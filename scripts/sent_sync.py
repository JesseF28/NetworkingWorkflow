#!/usr/bin/env python3
"""Compare Jesse's Sent Items with the Master Tracker and plan the sheet changes.

Commands:
  since   print the date to read Sent Items back to
  plan    --sent rows.txt --tracker tracker.xlsx-or-tool-result --out plan.json [--today YYYY-MM-DD]
  pending --plan plan.json     save planned rows to a CSV when the sheet can't be written
  done    --through YYYY-MM-DD record a finished sync

Sent rows are the lines read_sent_items.js returns:
  Thu 11/5/2026 2:19 PM | Tony Rosenberg; tony@prudence.vc | Subject | 1 | 0 | Hi Tony, ...
The two digits mean: thread has an outside sender, row is a calendar item.

plan.json holds only proposed changes. Nothing here touches the sheet.
"""
import argparse
import base64
import csv
import datetime as dt
import difflib
import io
import json
import re
import sys
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE.parent / "config.json").read_text(encoding="utf-8"))

COLUMNS = ["Contact", "Firm", "Stage", "Next action", "Email", "Email confidence", "Role / focus",
           "Vanderbilt class", "Location", "Last touch", "Target date (source)", "AUM / evidence",
           "Notes & history", "Sources"]
COL = {name: i for i, name in enumerate(COLUMNS)}
LETTER = {name: "ABCDEFGHIJKLMN"[i] for i, name in enumerate(COLUMNS)}

# Stage only moves forward. Delivery failed sits outside this order on purpose.
RANK = {"Research": 0, "Hold": 0, "Draft saved": 0, "Scheduled — confirm sent": 0,
        "Initial email sent": 1, "Reply received": 2, "Call scheduled": 3,
        "Outcome to confirm": 4, "Call completed": 5, "Closed / no response": 6}
NEXT_ACTION = {
    "Initial email sent": "Check for reply; follow up once if appropriate.",
    "Reply received": "Read the reply and set up a call if one isn't booked.",
    "Call scheduled": "Take the call, then send a thank-you.",
    "Call completed": "Record call notes; keep in touch if appropriate.",
    "Delivery failed": "Find a working address before trying again.",
}
GENERIC_DOMAINS = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "aol.com", "me.com"}
FIRM_NOISE = {"capital", "partners", "partner", "group", "management", "mgmt", "ventures", "venture", "equity",
              "investments", "investment", "holdings", "advisors", "advisers", "fund", "funds", "growth",
              "the", "and", "llc", "lp", "inc", "project", "level", "team", "startup"}
NICKNAMES = [{"mike", "michael"}, {"ben", "benjamin"}, {"zack", "zach", "zachary"}, {"will", "william", "bill"},
             {"rob", "robert", "bob"}, {"alex", "alexander", "alexandra"}, {"nick", "nicholas"},
             {"matt", "matthew"}, {"dave", "david"}, {"chris", "christopher"}, {"tony", "anthony"},
             {"tom", "thomas"}, {"jim", "james"}, {"joe", "joseph"}, {"dan", "daniel"}, {"sam", "samuel"},
             {"kate", "katie", "katherine"}, {"jon", "jonathan"}, {"andy", "andrew"}]


def norm(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def same_first(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    return a == b or any(a in g and b in g for g in NICKNAMES)


def fmt_date(d):
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def parse_sheet_date(s):
    s = str(s or "").strip()
    for f in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def emails_in(s):
    return [e.lower() for e in re.findall(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+", str(s or ""))]


# ---------------------------------------------------------------- reading inputs

def read_sent(path):
    rows = []
    pat = re.compile(r"^(?P<when>.+?) \| (?P<to>.*?) \| (?P<subject>.*) \| (?P<ext>[01]) \| (?P<meet>[01])(?: \| (?P<preview>.*))?$")
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        m = pat.match(line.strip())
        if not m:
            sys.exit(f"Line {n} of the sent rows doesn't match the expected format: {line[:90]}")
        when = re.sub(r"^[A-Za-z]{3} ", "", m["when"].strip())
        try:
            stamp = dt.datetime.strptime(when, "%m/%d/%Y %I:%M %p")
        except ValueError:
            sys.exit(f"Line {n} has a date I can't read: {m['when']}")
        parts = [p.strip() for p in m["to"].split(";") if p.strip()]
        preview = (m["preview"] or "").strip()
        g = re.match(r"(?:Hi|Hello|Hey|Dear)\s+([A-Z][\w.'-]*)", preview)
        rows.append({"when": stamp, "date": stamp.date(), "subject": m["subject"].strip(),
                     "external": m["ext"] == "1", "meeting": m["meet"] == "1", "preview": preview,
                     "greeting": g[1] if g else "",
                     "emails": [p.lower() for p in parts if "@" in p],
                     "names": [p for p in parts if "@" not in p]})
    return rows


def load_xlsx(path):
    raw = Path(path).read_bytes()
    if raw[:2] == b"PK":
        return openpyxl.load_workbook(io.BytesIO(raw))
    data = json.loads(raw.decode("utf-8"))          # saved Drive tool result
    return openpyxl.load_workbook(io.BytesIO(base64.b64decode(data["content"])))


def read_tab(wb, title):
    ws = wb[title]
    head = [c.value for c in ws[1]][:len(COLUMNS)]
    if head != COLUMNS:
        sys.exit(f"The {title} tab's columns have changed, so stop rather than write to the wrong ones.\n"
                 f"Expected {COLUMNS}\nFound    {head}")
    out = []
    for i, r in enumerate(ws.iter_rows(min_row=2, max_col=len(COLUMNS), values_only=True), 2):
        if r[0]:
            cells = ["" if v is None else fmt_date(v) if isinstance(v, (dt.date, dt.datetime)) else str(v) for v in r]
            out.append({"tab": title, "row": i, "cells": cells})
    return out


def read_draft_names(wb):
    """The Drafts & Notes tab records who each drafted email was for."""
    out = {}
    if "Drafts & Notes" not in wb.sheetnames:
        return out
    ws = wb["Drafts & Notes"]
    head = [c.value for c in ws[1]]
    if "Contact / section" not in head or "Recipient as recorded" not in head:
        return out
    name_i, to_i = head.index("Contact / section"), head.index("Recipient as recorded")
    for r in ws.iter_rows(min_row=2, values_only=True):
        for e in emails_in(r[to_i]):
            if r[name_i]:
                out.setdefault(e, {"name": str(r[name_i]).strip()})
    return out


def read_people_csv(path, name_col="name"):
    out = {}
    p = Path(path)
    if not p.exists():
        return out
    with p.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            for e in emails_in(r.get("email")):
                out[e] = r
    return out


# ---------------------------------------------------------------- deciding what a row is

def external_part(row):
    """Drop Vanderbilt, self and family recipients. Directory names look like 'Young, Maren'."""
    ignore_a = {a.lower() for a in CONFIG["ignore_addresses"]}
    ignore_n = {n.lower() for n in CONFIG["ignore_names"]}
    emails = [e for e in row["emails"] if not e.endswith("vanderbilt.edu") and e not in ignore_a]
    names = [n for n in row["names"] if "," not in n and " " in n and n.lower() not in ignore_n]
    return emails, names


def looks_like_networking(row):
    return bool(re.search(r"vanderbilt (freshman|student)|interested in|your (path|career)|thank you|thanks|"
                          r"curious about|coffee chat|student opportunit|internship|<>|meeting|chat",
                          row["subject"], re.I))


def subject_name(row):
    m = re.search(r"[—–-]\s*([A-Z][\w'-]+ [A-Z][\w'-]+)\s*$", row["subject"])
    return m[1] if m and "Jesse" not in m[1] else ""


def stage_signal(row):
    subject = row["subject"]
    if row["meeting"]:
        return None if subject.lower().startswith("declined") else "Call scheduled"
    if re.match(r"\s*(thank you|thanks)", subject, re.I):
        return "Call completed"
    return "Reply received" if row["external"] else "Initial email sent"


def firm_matches(domain, firm):
    root = norm(domain.split(".")[0])
    if not root or not firm:
        return False
    tokens = [norm(t) for t in re.split(r"[\s/&,()-]+", firm)]
    tokens = [t for t in tokens if len(t) >= 4 and t not in FIRM_NOISE]
    if any(t in root for t in tokens):
        return True
    return any(difflib.SequenceMatcher(None, t, root).ratio() >= 0.8 for t in tokens)


def local_fits_name(local, contact):
    """Common address shapes: first, first.last, flast, firstl, lastf, initials."""
    parts = [norm(p) for p in re.sub(r"\(.*?\)", "", contact).split()]
    parts = [p for p in parts if p]
    if not parts:
        return False
    first, last = parts[0], parts[-1]
    loc = norm(local)
    shapes = {first, last, first + last, first[0] + last, first + last[0], last + first[0], first[0] + last[0]}
    return loc in shapes and len(parts) > 1 or loc == first


class Matcher:
    def __init__(self, people):
        self.people = people
        self.by_email, self.by_name = {}, {}
        for p in people:
            for e in emails_in(p["cells"][COL["Email"]]):
                self.by_email.setdefault(e, p)
            self.by_name.setdefault(self.key(p["cells"][0]), p)

    @staticmethod
    def key(name):
        return norm(re.sub(r"\(.*?\)", "", name))

    def find(self, emails, names, greeting):
        """Returns (person, how) or (None, why-unsure). Contacted is listed first, so it wins ties."""
        for e in emails:
            if e in self.by_email:
                return self.by_email[e], "email"
        for n in names:
            if self.key(n) in self.by_name:
                return self.by_name[self.key(n)], "name"
        hits = []
        for p in self.people:
            contact = p["cells"][0]
            first = (re.sub(r"\(.*?\)", "", contact).split() or [""])[0]
            last = (re.sub(r"\(.*?\)", "", contact).split() or [""])[-1]
            for n in names:      # Benjamin Koch vs Ben Koch
                bits = n.split()
                if norm(bits[-1]) == norm(last) and same_first(bits[0], first):
                    hits.append(p)
            for e in emails:     # akim@catalur.com vs Alex Kim, Catalur Capital
                local, domain = e.split("@")
                if domain in GENERIC_DOMAINS:
                    continue
                if not firm_matches(domain, p["cells"][COL["Firm"]]):
                    continue
                if (greeting and same_first(greeting, first)) or local_fits_name(local, contact):
                    hits.append(p)
        unique = {id(h): h for h in hits}
        if len(unique) == 1:
            return next(iter(unique.values())), "firm + name"
        if len(unique) > 1:
            return None, "could be " + " or ".join(h["cells"][0] for h in unique.values())
        return None, ""


# ---------------------------------------------------------------- building the plan

def text_cell(v):
    """Keep Sheets from turning dates and class years into numbers or formulas."""
    v = "" if v is None else str(v)
    if v and (re.match(r"^[=+\-@]", v) or re.match(r"^[\d/.,\s-]+$", v) or parse_sheet_date(v)):
        return "'" + v
    return v


def history_line(rows, today):
    parts = []
    for r in sorted(rows, key=lambda x: x["when"]):
        to = (r["emails"] or r["names"] or ["?"])[0]
        parts.append(f"{fmt_date(r['date'])}: \"{r['subject']}\" to {to}")
    return f"Sent Items sync {fmt_date(today)}\n" + "\n".join(parts)


def add_note(existing, line):
    return (existing.rstrip() + "\n\n" + line) if existing.strip() else line


def add_source(existing):
    url = CONFIG["outlook_sent_url"]
    if url in existing:
        return existing
    return (existing.rstrip() + "\n" + url) if existing.strip() else url


def firm_from_domain(domain):
    """A first guess only. Rows carry firm_guessed so the run can look up the real name."""
    bits = domain.lower().split(".")
    root, tld = bits[0], bits[-1]
    if len(root) <= 3:
        return root.upper()
    root = root.replace("-", " ")
    m = re.match(r"^(.+?)(capital|cap|partners|ventures|management|mgmt|group|equity)$", root)
    words = [m[1].strip(), {"cap": "capital", "mgmt": "management"}.get(m[2], m[2])] if m else [root]
    if tld == "capital" and "capital" not in words:
        words.append("capital")
    if tld == "vc" and "ventures" not in words:
        words.append("ventures")
    return " ".join(words).title()


def best_stage(rows, current=""):
    best = current if current in RANK else ""
    for r in rows:
        s = stage_signal(r)
        if s and RANK[s] > RANK.get(best, -1):
            best = s
    return best or "Initial email sent"


def new_contact_row(rows, name_by_email, log, pool, drafts, today):
    emails = [e for r in rows for e in external_part(r)[0]]
    email = emails[-1] if emails else ""
    ref = log.get(email) or pool.get(email) or {}
    name = ref.get("name") or name_by_email.get(email, "") or drafts.get(email, {}).get("name", "")
    name = name or next((subject_name(r) for r in rows if subject_name(r)), "")
    domain = email.split("@")[1] if "@" in email else ""
    firm = ref.get("firm") or ("" if domain in GENERIC_DOMAINS else firm_from_domain(domain))
    greeting = next((r["greeting"] for r in rows if r["greeting"]), "")
    incomplete = not name
    if not name:
        short = greeting or email.split("@")[0]
        name = f"{short} ({firm})" if firm else short
    last = max(r["date"] for r in rows)
    stage = best_stage(rows)
    cells = [""] * len(COLUMNS)
    cells[COL["Contact"]] = name
    cells[COL["Firm"]] = firm
    cells[COL["Stage"]] = stage
    cells[COL["Next action"]] = NEXT_ACTION.get(stage, "")
    cells[COL["Email"]] = email
    cells[COL["Email confidence"]] = ref.get("email_confidence") or "Used in recorded outreach; see delivery notes"
    cells[COL["Role / focus"]] = " / ".join(x for x in [ref.get("title"), ref.get("strategy")] if x)
    cells[COL["Vanderbilt class"]] = ref.get("grad_year") or ""
    cells[COL["Location"]] = ref.get("location") or ""
    cells[COL["Last touch"]] = fmt_date(last)
    cells[COL["Target date (source)"]] = fmt_date(last + dt.timedelta(days=CONFIG["follow_up_days"]))
    aum = ref.get("aum_musd")
    cells[COL["AUM / evidence"]] = f"${aum}M" if aum else ""
    cells[COL["Notes & history"]] = history_line(rows, today)
    cells[COL["Sources"]] = CONFIG["outlook_sent_url"]
    return cells, incomplete, bool(firm) and not ref.get("firm")


def apply_to_existing(person, rows, today):
    """Returns (new cells, list of changed column names, flag text)."""
    cells = list(person["cells"])
    changed, flag = [], ""
    last_sent = max(r["date"] for r in rows)
    old_touch = parse_sheet_date(cells[COL["Last touch"]])
    old_stage = cells[COL["Stage"]]
    is_move = person["tab"] == CONFIG["prospects_tab"]
    new_emails = sorted({e for r in rows for e in external_part(r)[0]})

    if old_touch is None or last_sent > old_touch:
        cells[COL["Last touch"]] = fmt_date(last_sent)
        cells[COL["Target date (source)"]] = fmt_date(last_sent + dt.timedelta(days=CONFIG["follow_up_days"]))
        changed += ["Last touch", "Target date (source)"]

    if old_stage == "Delivery failed":
        if old_touch and last_sent > old_touch:
            flag = "Marked Delivery failed but emailed again later; left the Stage for you to check."
    else:
        stage = best_stage(rows, "" if is_move else old_stage)
        if stage != old_stage:
            cells[COL["Stage"]] = stage
            cells[COL["Next action"]] = NEXT_ACTION.get(stage, cells[COL["Next action"]])
            changed += ["Stage", "Next action"]

    sheet_emails = emails_in(cells[COL["Email"]])
    if not sheet_emails and new_emails:
        cells[COL["Email"]] = new_emails[0]
        if cells[COL["Email confidence"]] in ("", "Email needed"):
            cells[COL["Email confidence"]] = "Used in recorded outreach; see delivery notes"
            changed.append("Email confidence")
        changed.append("Email")
    extra = [e for e in new_emails if e not in sheet_emails and sheet_emails]
    if extra and not flag:
        flag = f"Sheet has {sheet_emails[0]}, but mail also went to {', '.join(extra)}."

    if changed or is_move:
        cells[COL["Notes & history"]] = add_note(cells[COL["Notes & history"]], history_line(rows, today))
        cells[COL["Sources"]] = add_source(cells[COL["Sources"]])
        changed += ["Notes & history", "Sources"]
    return cells, changed, flag


def read_bounced(path):
    """Rows from the Outlook search for 'undeliverable'. Keep only real bounce notices."""
    if not path:
        return set()
    out = set()
    for r in read_sent(path):
        if re.search(r"deliver|Office365Logo|your message", r["preview"], re.I):
            out.update(r["emails"])
    return out


def all_bounced(rows, bounced):
    """Bounced only if every address used failed and nobody answered."""
    used = {e for r in rows for e in external_part(r)[0]}
    answered = any(stage_signal(r) not in ("Initial email sent", None) for r in rows)
    return bool(used) and used <= bounced and not answered


def build_plan(args):
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    wb = load_xlsx(args.tracker)
    contacted = read_tab(wb, CONFIG["contacted_tab"])
    prospects = read_tab(wb, CONFIG["prospects_tab"])
    log = read_people_csv(CONFIG["prospect_log_csv"])
    pool = read_people_csv(CONFIG["prospect_pool_csv"])
    drafts = read_draft_names(wb)
    matcher = Matcher(contacted + prospects)
    rows = read_sent(args.sent)
    bounced = read_bounced(args.bounced)

    # A display name on one row tells us who a bare address on another row is.
    name_by_email, email_by_name = {}, {}
    for r in rows:
        emails, names = external_part(r)
        if len(emails) == 1 and names:
            name_by_email[emails[0]] = names[-1]
            for n in names:
                email_by_name[n.lower()] = emails[0]

    skipped, review = 0, []
    matched, fresh = {}, {}
    for r in rows:
        emails, names = external_part(r)
        if not emails and not names:
            skipped += 1
            continue
        if r["meeting"] and not emails and not any(n.lower() in email_by_name or matcher.key(n) in matcher.by_name for n in names):
            skipped += 1
            continue
        lookup_names = names + [name_by_email[e] for e in emails if e in name_by_email]
        lookup_names += [subject_name(r)] if subject_name(r) else []
        lookup_names += [log[e]["name"] for e in emails if e in log and log[e].get("name")]
        lookup_names += [pool[e]["name"] for e in emails if e in pool and pool[e].get("name")]
        lookup_names += [drafts[e]["name"] for e in emails if e in drafts]
        person, how = matcher.find(emails, lookup_names, r["greeting"])
        if person:
            matched.setdefault(id(person), (person, []))[1].append(r)
        elif how:
            review.append({"who": (emails or names)[0], "subject": r["subject"], "date": fmt_date(r["date"]),
                           "reason": how})
        elif looks_like_networking(r):
            address = next(iter(emails), None) or next((email_by_name[n.lower()] for n in names if n.lower() in email_by_name), None)
            key = address or names[0].lower()
            fresh.setdefault(key, []).append(r)
        else:
            review.append({"who": (emails or names)[0], "subject": r["subject"], "date": fmt_date(r["date"]),
                           "reason": "outside address, but the subject doesn't look like networking"})

    new_rows, updates, deletes, flags, incomplete = [], [], [], [], []
    warned = set()
    for r in rows:
        for e in external_part(r)[0]:
            audit = (log.get(e) or {}).get("audit", "")
            if audit.upper().startswith("DON'T EMAIL") and e not in warned:
                warned.add(e)
                flags.append({"who": log[e].get("name") or e, "note": f"Emailed {fmt_date(r['date'])}, but the prospect log says: {audit}"})
    for person, prs in matched.values():
        cells, changed, flag = apply_to_existing(person, prs, today)
        name = person["cells"][0]
        if all_bounced(prs, bounced) and cells[COL["Stage"]] != "Delivery failed":
            cells[COL["Stage"]] = "Delivery failed"
            cells[COL["Next action"]] = NEXT_ACTION["Delivery failed"]
            changed += ["Stage", "Next action"]
        if flag:
            flags.append({"who": name, "note": flag})
        if person["tab"] == CONFIG["prospects_tab"]:
            new_rows.append({"source": "moved from Prospects", "contact": name, "cells": cells,
                             "prior_stage": person["cells"][COL["Stage"]]})
            deletes.append({"contact": name, "row": person["row"]})
        elif changed:
            updates.append({"contact": name, "row": person["row"], "changed": changed,
                            "stage": [person["cells"][COL["Stage"]], cells[COL["Stage"]]],
                            "cells": [{"range": f"'{CONFIG['contacted_tab']}'!{LETTER[c]}{person['row']}",
                                       "value": text_cell(cells[COL[c]])} for c in dict.fromkeys(changed)]})
    for key, prs in fresh.items():
        cells, part, firm_guessed = new_contact_row(prs, name_by_email, log, pool, drafts, today)
        if all_bounced(prs, bounced):
            cells[COL["Stage"]] = "Delivery failed"
            cells[COL["Next action"]] = NEXT_ACTION["Delivery failed"]
        new_rows.append({"source": "new", "contact": cells[0], "cells": cells,
                         "name_incomplete": part, "firm_guessed": firm_guessed})
        if part:
            incomplete.append(cells[0])

    new_rows.sort(key=lambda x: x["contact"].lower())
    deletes.sort(key=lambda x: -x["row"])
    last_row = max([p["row"] for p in contacted] + [1])
    plan = {
        "today": today.isoformat(),
        "through": max((r["date"] for r in rows), default=today).isoformat(),
        "rows_read": len(rows), "skipped_not_networking": skipped,
        "contacted_last_data_row": last_row,
        "contacted_rows_needed_through": last_row + len(new_rows),
        "new_rows": new_rows,
        "new_rows_values": [[text_cell(c) for c in n["cells"]] for n in new_rows],
        "updates": updates,
        "prospect_rows_to_delete": deletes,
        "flags": flags, "review": review, "name_incomplete": incomplete,
    }
    Path(args.out).write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
    print_report(plan)


def print_report(p):
    moved = [n for n in p["new_rows"] if n["source"] != "new"]
    added = [n for n in p["new_rows"] if n["source"] == "new"]
    print(f"Read {p['rows_read']} sent rows; {p['skipped_not_networking']} were school, family or similar.")
    print(f"\nNEW TO THE SHEET ({len(added)})")
    for n in added:
        c = n["cells"]
        print(f"  {c[0]:34} {c[COL['Firm']][:26]:26} {c[COL['Stage']]:20} {c[COL['Last touch']]:13} {c[COL['Email']]}")
    print(f"\nMOVED FROM PROSPECTS ({len(moved)})")
    for n in moved:
        c = n["cells"]
        print(f"  {c[0]:34} {c[COL['Firm']][:26]:26} {n['prior_stage'][:12]:12} -> {c[COL['Stage']]:20} {c[COL['Last touch']]}")
    print(f"\nUPDATED ON CONTACTED ({len(p['updates'])})")
    for u in p["updates"]:
        fields = [c for c in u["changed"] if c not in ("Notes & history", "Sources", "Target date (source)", "Next action")]
        print(f"  {u['contact']:34} {u['stage'][0]} -> {u['stage'][1]}  [{', '.join(fields)}]")
    print(f"\nFLAGS ({len(p['flags'])})")
    for f in p["flags"]:
        print(f"  {f['who']}: {f['note']}")
    print(f"\nNEEDS A LOOK, NOT WRITTEN ({len(p['review'])})")
    for r in p["review"]:
        print(f"  {r['who']} | {r['subject'][:50]} | {r['date']} | {r['reason']}")
    if p["name_incomplete"]:
        print(f"\nLAST NAME UNKNOWN ({len(p['name_incomplete'])}): {', '.join(p['name_incomplete'])}")
    print(f"\nContacted data ends at row {p['contacted_last_data_row']}; new rows run through row {p['contacted_rows_needed_through']}.")


# ---------------------------------------------------------------- small commands

def state():
    p = Path(CONFIG["state_file"])
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def cmd_since(_):
    through = state().get("synced_through")
    if not through:
        print(CONFIG["first_sync_since"])
        return
    print((dt.date.fromisoformat(through) - dt.timedelta(days=CONFIG["overlap_days"])).isoformat())


def cmd_done(args):
    s = state()
    s["synced_through"] = args.through
    s["last_run"] = dt.date.today().isoformat()
    Path(CONFIG["state_file"]).write_text(json.dumps(s, indent=1), encoding="utf-8")
    print("Recorded", s)


def cmd_pending(args):
    p = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    out = Path(CONFIG["data_dir"]) / f"sent-sync-pending-{p['today']}.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Action"] + COLUMNS)
        for n in p["new_rows"]:
            w.writerow([n["source"]] + n["cells"])
        for u in p["updates"]:
            for c in u["cells"]:
                w.writerow([f"update {u['contact']} {c['range']}", c["value"]])
    print(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("since").set_defaults(fn=cmd_since)
    a = sub.add_parser("plan")
    a.add_argument("--sent", required=True)
    a.add_argument("--tracker", required=True)
    a.add_argument("--bounced", help="rows read from the Outlook search for undeliverable")
    a.add_argument("--out", required=True)
    a.add_argument("--today")
    a.set_defaults(fn=build_plan)
    b = sub.add_parser("pending")
    b.add_argument("--plan", required=True)
    b.set_defaults(fn=cmd_pending)
    c = sub.add_parser("done")
    c.add_argument("--through", required=True)
    c.set_defaults(fn=cmd_done)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
