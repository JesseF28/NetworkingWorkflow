"""Validate the week's prospects, render the Google Doc HTML, and log who was listed.

prospects.json is a list of objects with these fields:
  name, title, firm, strategy ("Private equity" | "Venture capital" | "Growth equity" | "Hedge fund"),
  location, vanderbilt (e.g. "B.A. Economics, 2022"),
  grad_year (number, 2020-2026 per config.json), grad_year_source (URL or "Inferred: ..." note),
  aum_musd (number, or "undisclosed" for a small firm with no public figure), aum_source (URL), profile_source (URL confirming role + Vanderbilt),
  email, email_confidence ("Verified (PitchBook)" | "Verified (public source)" |
                           "Pattern-matched (based on x@firm.com)" | "Guessed"),
  subject, body

Usage:
  python -I build_doc.py validate --prospects p.json --dnc dnc.json [--allow-short]
  python -I build_doc.py html --prospects p.json --out doc.html --week-of 2026-10-29 [--notes "..."]
  python -I build_doc.py log --prospects p.json --log prospect-log.csv --doc-url URL [--week-of 2026-10-29]
  python -I build_doc.py merge --log prospect-log.csv
"""
import argparse
import csv
import datetime as dt
import html
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dnc import conflicts, pending_paths  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
    CFG = json.load(f)

REQUIRED = ["name", "title", "firm", "strategy", "location", "vanderbilt", "grad_year", "grad_year_source", "aum_musd",
            "aum_source", "profile_source", "email", "email_confidence", "subject", "body"]
CONF_PREFIXES = ("Verified", "Pattern-matched", "Guessed")
LOG_FIELDS = ["week", "date_listed", "name", "title", "firm", "strategy", "aum_musd", "location", "vanderbilt", "grad_year", "audit",
              "email", "email_confidence", "subject", "doc_url"]


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cmd_validate(a):
    ps, dnc = load(a.prospects), load(a.dnc)
    errs, warns = [], []
    want = CFG["per_week"]
    if len(ps) != want and not (a.allow_short and len(ps) < want):
        errs.append(f"{len(ps)} prospects; need exactly {want}")
    seen_names, seen_emails = set(), set()
    for i, p in enumerate(ps, 1):
        tag = f"#{i} {p.get('name', '?')}"
        missing = [k for k in REQUIRED if p.get(k) in (None, "")]
        if missing:
            errs.append(f"{tag}: missing {', '.join(missing)}")
            continue
        try:
            year = int(p["grad_year"])
            if not CFG["grad_year_min"] <= year <= CFG["grad_year_max"]:
                errs.append(f"{tag}: class of {year} is outside {CFG['grad_year_min']}-{CFG['grad_year_max']}")
        except (TypeError, ValueError):
            errs.append(f"{tag}: grad_year '{p['grad_year']}' is not a year")
        if "@" not in p["email"]:
            errs.append(f"{tag}: email '{p['email']}' is not an address")
        if not p["email_confidence"].startswith(CONF_PREFIXES):
            errs.append(f"{tag}: email_confidence must start with Verified / Pattern-matched / Guessed")
        try:
            aum = 0 if p["aum_musd"] == "undisclosed" else float(p["aum_musd"])
            if aum >= CFG["max_aum_musd"]:
                errs.append(f"{tag}: AUM ${aum:,.0f}M is not under ${CFG['max_aum_musd']:,}M")
        except (TypeError, ValueError):
            errs.append(f"{tag}: aum_musd '{p['aum_musd']}' is not a number")
        for h in conflicts(p, dnc):
            errs.append(f"{tag}: on do-not-contact list ({h})")
        key = p["name"].strip().lower()
        if key in seen_names or p["email"].lower() in seen_emails:
            errs.append(f"{tag}: duplicate within this week's list")
        seen_names.add(key)
        seen_emails.add(p["email"].lower())
        body = p["body"]
        first = p["name"].split()[0]
        if not body.lstrip().startswith("Hi "):
            errs.append(f"{tag}: body should open with 'Hi <first name>,'")
        elif not body.lstrip().startswith(f"Hi {first}") and not a.allow_nickname:
            warns.append(f"{tag}: greeting doesn't use '{first}' (fine if it's their nickname)")
        if CFG["availability"] not in body:
            errs.append(f"{tag}: availability line from config.json is missing or edited")
        if not body.rstrip().endswith(CFG["sender"]["name"]):
            errs.append(f"{tag}: body should end with the signature '{CFG['sender']['name']}'")
        if "{" in body or "}" in body or "{" in p["subject"]:
            errs.append(f"{tag}: unfilled template placeholder")
        words = len(body.split())
        if not 90 <= words <= 200:
            warns.append(f"{tag}: body is {words} words (template is ~120-150)")
    for firm, n in Counter(p.get("firm", "").strip().lower() for p in ps).items():
        if n > CFG["max_per_firm"]:
            errs.append(f"{n} people from '{firm}'; max {CFG['max_per_firm']} per firm")
    guessed = sum(1 for p in ps if str(p.get("email_confidence", "")).startswith("Guessed"))
    if guessed > 6:
        warns.append(f"{guessed} emails are Guessed; try to replace some with better-evidenced people")
    for w in warns:
        print("WARN ", w)
    for e in errs:
        print("ERROR", e)
    print("PASS" if not errs else f"FAIL ({len(errs)} errors)")
    sys.exit(1 if errs else 0)


def aum_text(p, money=False):
    if p["aum_musd"] == "undisclosed":
        return "undisclosed"
    n = f"{float(p['aum_musd']):,.0f}"
    return f"${n}M" if money else n


def esc(s):
    return html.escape(str(s))


def para_html(text):
    # One <p> per paragraph with a bottom margin, so pasting into Outlook gives single blank lines.
    paras = [p for p in text.strip().split("\n\n") if p.strip()]
    return "".join(f"<p style='margin:0 0 10pt 0'>{'<br>'.join(esc(l) for l in p.split(chr(10)))}</p>"
                   for p in paras)


def cmd_html(a):
    ps = load(a.prospects)
    week = dt.date.fromisoformat(a.week_of)
    title = f"Networking prospects — week of {week.strftime('%b')} {week.day}, {week.year}"
    conf = Counter(p["email_confidence"].split(" ")[0] for p in ps)
    out = [
        "<html><head><meta charset='utf-8'></head><body style='font-family:Arial'>",
        f"<h1>{esc(title)}</h1>",
        f"<p>{len(ps)} new Vanderbilt alumni (classes of {CFG['grad_year_min']}-{CFG['grad_year_max']}) at PE / VC / growth / hedge fund firms under "
        f"${CFG['max_aum_musd'] / 1000:.1f}B AUM, none previously contacted ({sum(1 for p in ps if p['location'].rstrip().endswith(('NY', 'NJ', 'CT')))} in NY/NJ/CT). "
        f"Emails: {conf.get('Verified', 0)} verified, {conf.get('Pattern-matched', 0)} pattern-matched, "
        f"{conf.get('Guessed', 0)} guessed.</p>",
    ]
    if a.notes:
        out.append(f"<p><b>Run notes:</b> {esc(a.notes)}</p>")
    out.append("<h2>Summary</h2><table border='1' cellpadding='4' style='border-collapse:collapse'>"
               "<tr><th>#</th><th>Name</th><th>Class</th><th>Title</th><th>Firm</th><th>Strategy</th>"
               "<th>AUM ($M)</th><th>Location</th><th>Email</th><th>Email confidence</th></tr>")
    for i, p in enumerate(ps, 1):
        out.append(
            f"<tr><td>{i}</td><td>{esc(p['name'])}</td><td>{esc(p['grad_year'])}</td><td>{esc(p['title'])}</td><td>{esc(p['firm'])}</td>"
            f"<td>{esc(p['strategy'])}</td><td>{aum_text(p)}</td><td>{esc(p['location'])}</td>"
            f"<td>{esc(p['email'])}</td><td>{esc(p['email_confidence'])}</td></tr>")
    out.append("</table><h2>Emails</h2>")
    for i, p in enumerate(ps, 1):
        out += [
            f"<h3>{i}. {esc(p['name'])} — {esc(p['title'])}, {esc(p['firm'])}</h3>",
            f"<p><b>To:</b> {esc(p['email'])} &nbsp;<i>({esc(p['email_confidence'])})</i></p>",
            f"<p><b>Subject:</b> {esc(p['subject'])}</p>",
            "<p><b>Body:</b></p>",
            para_html(p["body"]),
            f"<p style='color:#666;font-size:9pt'>Vanderbilt: {esc(p['vanderbilt'])} · Class of {esc(p['grad_year'])} ({esc(p['grad_year_source'])}) · {esc(p['location'])} · "
            f"AUM {aum_text(p, money=True)} (<a href='{esc(p['aum_source'])}'>source</a>) · "
            f"<a href='{esc(p['profile_source'])}'>profile</a></p>",
            "<p>&nbsp;</p>",
        ]
    out.append("</body></html>")
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"wrote {a.out} — title: {title}")


def read_log(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def iso_date(value):
    # Excel rewrites dates as 10/30/2026 if the log is saved there.
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return value.strip()


def write_log(path, rows):
    """Rewrite the log sorted by date, numbering each distinct run date as a week."""
    seen, unique = set(), []
    for r in rows:
        r["date_listed"] = iso_date(r.get("date_listed") or "")
        key = (r["date_listed"], (r.get("email") or r.get("name") or "").strip().lower())
        if key not in seen:
            seen.add(key)
            unique.append(r)
    unique.sort(key=lambda r: r["date_listed"])
    weeks = {d: i for i, d in enumerate(sorted({r["date_listed"] for r in unique}), 1)}
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=LOG_FIELDS, extrasaction="ignore")
            w.writeheader()
            for r in unique:
                d = dt.date.fromisoformat(r["date_listed"])
                label = f"Week {weeks[r['date_listed']]} ({d.strftime('%b')} {d.day}, {d.year})"
                w.writerow({**r, "week": label})
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return len(unique), len(weeks)


def merge_log(log, new):
    """Fold new rows and any pending files into the log; if it's locked, keep the rows pending."""
    pending = pending_paths(log)
    rows = read_log(log) + [r for p in pending for r in read_log(p)] + new
    try:
        n, weeks = write_log(log, rows)
    except PermissionError:
        print(f"LOCKED: {log} is open in another program (usually Excel); nothing merged.")
        if new:
            base, ext = os.path.splitext(log)
            path = f"{base}-pending-{new[0]['date_listed']}{ext}"
            write_log(path, read_log(path) + new)
            print(f"saved {len(new)} prospects to {path}; the next run merges them.")
        return
    for p in pending:
        os.replace(p, p + ".merged")
    print(f"{log}: {n} prospects across {weeks} weeks ({len(new)} new, {len(pending)} pending files merged)")


def cmd_log(a):
    merge_log(a.log, [{**p, "date_listed": a.week_of, "doc_url": a.doc_url} for p in load(a.prospects)])


def cmd_merge(a):
    merge_log(a.log, [])


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--prospects", required=True)
    v.add_argument("--dnc", required=True)
    v.add_argument("--allow-short", action="store_true")
    v.add_argument("--allow-nickname", action="store_true")
    h = sub.add_parser("html")
    h.add_argument("--prospects", required=True)
    h.add_argument("--out", required=True)
    h.add_argument("--week-of", required=True)
    h.add_argument("--notes", default="")
    lg = sub.add_parser("log")
    lg.add_argument("--prospects", required=True)
    lg.add_argument("--log", required=True)
    lg.add_argument("--doc-url", required=True)
    lg.add_argument("--week-of", default=dt.date.today().isoformat())
    m = sub.add_parser("merge")
    m.add_argument("--log", required=True)
    a = p.parse_args()
    {"validate": cmd_validate, "html": cmd_html, "log": cmd_log, "merge": cmd_merge}[a.cmd](a)


if __name__ == "__main__":
    main()
