"""Do-not-contact list for weekly networking prospects.

build: collect every name and email from the tracker sheet (all tabs), the local
       prospect log, past weekly docs, and any extra text files.
check: flag candidates whose name or email is already on that list.

Usage:
  python -I dnc.py build --sheet <xlsx | Drive tool-result json> [more ...] [--log csv] [--docs txt ...] [--extra txt ...] --out dnc.json
  python -I dnc.py check --dnc dnc.json --candidates candidates.json
"""
import argparse
import base64
import csv
import glob
import json
import os
import re
import sys
import tempfile
import unicodedata

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
NAME_HEADERS = {"name", "contact", "prospect"}
SKIP_NAME_VALUES = {"other names in source", "name", "contact", "prospect"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "cfa", "cpa", "mba", "phd"}


def norm_tokens(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"\(.*?\)", " ", s)  # nicknames in parentheses
    s = re.sub(r"[^a-zA-Z\s-]", " ", s).lower().replace("-", " ")
    return [t for t in s.split() if t and t not in SUFFIXES and len(t) > 1]


def name_keys(name):
    """(first, x) for every later token, so middle/maiden names still match."""
    t = norm_tokens(name)
    if len(t) < 2:
        return set()
    return {f"{t[0]}|{x}" for x in t[1:]}


def load_xlsx(path):
    import openpyxl

    if path.lower().endswith((".json", ".txt")):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        fd, tmp = tempfile.mkstemp(suffix=".xlsx")
        with os.fdopen(fd, "wb") as out:
            out.write(base64.b64decode(data["content"]))
        path = tmp
    return openpyxl.load_workbook(path, data_only=True)


def from_sheet(path):
    names, emails = set(), set()
    wb = load_xlsx(path)
    for ws in wb:
        name_cols = None
        for row in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c).strip() for c in row]
            for c in cells:
                emails.update(e.lower() for e in EMAIL_RE.findall(c))
            lowered = [c.lower() for c in cells]
            if name_cols is None:
                cols = [i for i, c in enumerate(lowered) if c in NAME_HEADERS]
                if cols:
                    name_cols = cols
                continue
            for i in name_cols:
                if (i < len(cells) and cells[i] and cells[i].lower() not in SKIP_NAME_VALUES
                        and len(norm_tokens(cells[i])) <= 5):  # skip note rows
                    names.add(cells[i])
    return names, emails


def pending_paths(log):
    """Rows saved beside the log while it was locked (see build_doc.py merge_log)."""
    base, ext = os.path.splitext(log)
    return sorted(glob.glob(f"{glob.escape(base)}-pending-*{ext}"))


def from_log(path):
    names, emails = set(), set()
    if not path:
        return names, emails
    for p in [path] + pending_paths(path):
        if os.path.exists(p):
            with open(p, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    if r.get("name"):
                        names.add(r["name"].strip())
                    if r.get("email"):
                        emails.add(r["email"].strip().lower())
    return names, emails


def from_text(paths):
    """Past weekly docs / Outlook notes: emails anywhere, names from 'Name — ' headings."""
    names, emails = set(), set()
    for p in paths or []:
        with open(p, encoding="utf-8") as f:
            text = f.read()
        emails.update(e.lower() for e in EMAIL_RE.findall(text))
        for m in re.finditer(r"^\W*\d{1,2}\.\s+([A-Z][^\n—–|,]{2,60}?)\s+[—–|-]", text, re.M):
            names.add(m.group(1).strip())
    return names, emails


def cmd_build(a):
    names, emails = set(), set()
    for path in a.sheet:
        n, e = from_sheet(path)
        names |= n
        emails |= e
    n_sheet = len(names)
    for n, e in (from_log(a.log), from_text(a.docs), from_text(a.extra)):
        names |= n
        emails |= e
    keys = set()
    for n in names:
        keys |= name_keys(n)
    out = {"names": sorted(names), "emails": sorted(emails), "name_keys": sorted(keys)}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"do-not-contact: {len(names)} names ({n_sheet} from sheet), {len(emails)} emails -> {a.out}")
    if n_sheet < 40:
        print("WARNING: fewer than 40 names from the sheet; the download may be incomplete.", file=sys.stderr)


def conflicts(person, dnc):
    hits = []
    email = (person.get("email") or "").strip().lower()
    if email and email in set(dnc["emails"]):
        hits.append(f"email {email} already contacted")
    k = name_keys(person.get("name", "")) & set(dnc["name_keys"])
    if k:
        match = [n for n in dnc["names"] if name_keys(n) & k]
        hits.append(f"name matches {match[:3] or sorted(k)}")
    return hits + loose_matches(person, dnc)


def loose_matches(person, dnc):
    """Catch 'Alex Brown' vs 'Alexander Brown', and a guessed address for someone already listed at that firm."""
    t = norm_tokens(person.get("name", ""))
    if len(t) < 2:
        return []
    first, last = t[0], t[-1]
    hits = []
    for n in dnc["names"]:
        u = norm_tokens(n)
        if (len(u) >= 2 and last in u[1:] and first != u[0] and min(len(first), len(u[0])) >= 3
                and (first.startswith(u[0]) or u[0].startswith(first))):
            hits.append(f"name resembles {n}")
    domain = (person.get("email") or "").strip().lower().partition("@")[2]
    if domain and len(last) >= 3:
        for e in dnc["emails"]:
            local, _, d = e.partition("@")
            if d == domain and (local.endswith(last) or local.startswith(last)) and e != person["email"].strip().lower():
                hits.append(f"same firm and surname as {e}")
    return hits


def cmd_check(a):
    with open(a.dnc, encoding="utf-8") as f:
        dnc = json.load(f)
    with open(a.candidates, encoding="utf-8") as f:
        cands = json.load(f)
    bad = 0
    for c in cands:
        h = conflicts(c, dnc)
        if h:
            bad += 1
            print(f"DROP  {c.get('name')} ({c.get('firm', '')}): {'; '.join(h)}")
    print(f"{len(cands) - bad} of {len(cands)} candidates are new.")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--sheet", required=True, nargs="+")
    b.add_argument("--log")
    b.add_argument("--docs", nargs="*")
    b.add_argument("--extra", nargs="*")
    b.add_argument("--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("--dnc", required=True)
    c.add_argument("--candidates", required=True)
    a = p.parse_args()
    {"build": cmd_build, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    main()
