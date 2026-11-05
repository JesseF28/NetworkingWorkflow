"""The outbox: every written email, from "needs approval" through "scheduled".

It carries a run's emails between sessions (the Tuesday run writes them, a later
chat schedules them), enforces that nothing is scheduled without Jesse's approval,
and lets an interrupted scheduling run pick up where it stopped.

Status flow:
  needs_approval -> approved -> scheduled
                             -> draft_saved -> scheduled
                             -> unclear (Outlook gave an ambiguous result; `next` won't offer it)
                             -> failed
  any open status -> skipped

Usage (add --outbox PATH before the command to use a different file):
  python -I outbox.py add --prospects p.json --run-date 2026-11-10 [--doc-url URL]
  python -I outbox.py show [--run-date D] [--status S]
  python -I outbox.py approve (--verified | --all | --names "A B" "C D") [--run-date D]
  python -I outbox.py next
  python -I outbox.py mark --email x@y.com --status scheduled --scheduled-for "2026-11-11 12:00 ET" [--note N]
  python -I outbox.py sheet-rows --out rows.json [--new-only] [--run-date D]
  python -I outbox.py mark-sheet [--run-date D]
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
    CFG = json.load(f)

# Where each status may go next. Approval only happens through the `approve` command.
MOVES = {
    "needs_approval": {"skipped"},
    "approved": {"draft_saved", "scheduled", "unclear", "failed", "skipped"},
    "draft_saved": {"approved", "scheduled", "unclear", "failed", "skipped"},
    "unclear": {"approved", "draft_saved", "scheduled", "failed", "skipped"},
    "failed": {"approved", "skipped"},
    "scheduled": {"approved", "unclear", "failed", "skipped"},
    "skipped": set(),
}
# Going back to `approved` means sending it again, so say what Outlook showed.
NOTE_REQUIRED = {("unclear", "approved"), ("scheduled", "approved"), ("failed", "approved")}
SHEET_COLUMNS = ["Week", "Name", "Title", "Firm", "Strategy", "AUM $M", "Location", "Vanderbilt", "Email",
                 "Email confidence", "Subject", "Doc link", "Send status"]


def fail(msg):
    print(f"ERROR {msg}")
    sys.exit(1)


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, items):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=1, ensure_ascii=False)
    for attempt in range(5):  # OneDrive can hold the file for a moment while it syncs
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(1)


def key(email):
    return (email or "").strip().lower()


def selected(items, a):
    return [i for i in items if not getattr(a, "run_date", None) or i["run_date"] == a.run_date]


def tier(item):
    return item.get("email_confidence", "Guessed").split(" ")[0]


def cmd_add(a):
    with open(a.prospects, encoding="utf-8") as f:
        people = json.load(f)
    items = load(a.outbox)
    known = {key(i["email"]) for i in items}
    added = 0
    for p in people:
        missing = [k for k in ("name", "email", "subject", "body") if not p.get(k)]
        if missing:
            fail(f"{p.get('name', '?')}: missing {', '.join(missing)}; nothing added")
    for p in people:
        if key(p["email"]) in known:
            print(f"SKIP  {p['name']}: {p['email']} is already in the outbox")
            continue
        known.add(key(p["email"]))
        items.append({**p, "run_date": a.run_date, "doc_url": a.doc_url, "status": "needs_approval",
                      "approved_on": None, "scheduled_for": None, "on_sheet": False, "history": []})
        added += 1
    save(a.outbox, items)
    print(f"{added} added to {a.outbox}, waiting for approval.")


def cmd_show(a):
    items = [i for i in selected(load(a.outbox), a) if not a.status or i["status"] == a.status]
    if not items:
        print("The outbox has nothing matching that.")
        return
    print("Counts:", ", ".join(f"{s} {n}" for s, n in Counter(i["status"] for i in items).most_common()))
    for t in ("Verified", "Pattern-matched", "Guessed"):
        group = [i for i in items if tier(i) == t]
        if group:
            print(f"\n{t} ({len(group)}):")
        for i in group:
            when = f" for {i['scheduled_for']}" if i.get("scheduled_for") else ""
            print(f"  [{i['status']}{when}] {i['name']} ({i.get('firm', '')}) <{i['email']}> run {i['run_date']}")


def match_names(pool, names):
    hits = []
    for n in names:
        q = n.strip().lower()
        found = [i for i in pool if i["name"].lower() == q] or [i for i in pool if q in i["name"].lower()]
        if len(found) != 1:
            fail(f"'{n}' matches {len(found)} people waiting for approval; nothing approved")
        hits.append(found[0])
    return hits


def cmd_approve(a):
    items = load(a.outbox)
    pool = [i for i in selected(items, a) if i["status"] == "needs_approval"]
    if a.all:
        chosen = pool
    elif a.verified:
        chosen = [i for i in pool if tier(i) == "Verified"]
    else:
        chosen = match_names(pool, a.names)
    today = dt.date.today().isoformat()
    for i in chosen:
        i["status"], i["approved_on"] = "approved", today
        i["history"].append({"on": today, "status": "approved"})
    save(a.outbox, items)
    print(f"Approved {len(chosen)}: {', '.join(i['name'] for i in chosen) or 'nobody'}")
    risky = [i for i in chosen if tier(i) != "Verified"]
    if risky:
        print(f"Not verified, so these may bounce: {', '.join(i['name'] for i in risky)}")


def cmd_next(a):
    waiting = [i for i in load(a.outbox) if i["status"] == "approved"]
    if not waiting:
        print("Nothing approved is waiting.")
        return
    i = waiting[0]
    print(f"{len(waiting)} approved and waiting. Next:")
    print(json.dumps({k: i.get(k) for k in ("name", "firm", "email", "email_confidence", "subject", "body")},
                     indent=1, ensure_ascii=False))


def cmd_mark(a):
    items = load(a.outbox)
    found = [i for i in items if key(i["email"]) == key(a.email)]
    if not found:
        fail(f"{a.email} is not in the outbox")
    i = found[0]
    old = i["status"]
    if a.status not in MOVES[old]:
        fail(f"{i['name']} is '{old}' and can't move to '{a.status}'"
             + ("; Jesse has to approve it first" if old == "needs_approval" else ""))
    if (old, a.status) in NOTE_REQUIRED and not a.note:
        fail(f"moving {i['name']} from '{old}' back to 'approved' needs --note saying what Outlook showed")
    if a.status == "scheduled" and not a.scheduled_for:
        fail("--scheduled-for is required, as read back from Outlook")
    i["status"] = a.status
    i["scheduled_for"] = a.scheduled_for if a.status == "scheduled" else None
    i["history"].append({"on": dt.date.today().isoformat(), "status": a.status, "note": a.note})
    save(a.outbox, items)
    print(f"{i['name']}: {old} -> {a.status}")


def send_status(i):
    label = i["status"].replace("_", " ").capitalize()
    return f"{label} {i['scheduled_for']}" if i.get("scheduled_for") else label


def cmd_sheet_rows(a):
    rows = []
    for i in selected(load(a.outbox), a):
        if a.new_only and i.get("on_sheet"):
            continue
        rows.append([i["run_date"], i["name"], i.get("title", ""), i.get("firm", ""), i.get("strategy", ""),
                     i.get("aum_musd", ""), i.get("location", ""), i.get("vanderbilt", ""), i["email"],
                     i.get("email_confidence", ""), i["subject"], i.get("doc_url") or "", send_status(i)])
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"columns": SHEET_COLUMNS, "rows": rows}, f, indent=1, ensure_ascii=False)
    print(f"{len(rows)} rows -> {a.out}")


def cmd_mark_sheet(a):
    items = load(a.outbox)
    chosen = selected(items, a)
    for i in chosen:
        i["on_sheet"] = True
    save(a.outbox, items)
    print(f"{len(chosen)} marked as on the sheet.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--outbox", default=CFG["outbox_json"])
    sub = p.add_subparsers(dest="cmd", required=True)
    ad = sub.add_parser("add")
    ad.add_argument("--prospects", required=True)
    ad.add_argument("--run-date", default=dt.date.today().isoformat())
    ad.add_argument("--doc-url", default="")
    sh = sub.add_parser("show")
    sh.add_argument("--run-date")
    sh.add_argument("--status", choices=sorted(MOVES))
    ap = sub.add_parser("approve")
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--verified", action="store_true")
    who.add_argument("--all", action="store_true")
    who.add_argument("--names", nargs="+")
    ap.add_argument("--run-date")
    sub.add_parser("next")
    mk = sub.add_parser("mark")
    mk.add_argument("--email", required=True)
    mk.add_argument("--status", required=True, choices=sorted(MOVES))
    mk.add_argument("--scheduled-for")
    mk.add_argument("--note")
    sr = sub.add_parser("sheet-rows")
    sr.add_argument("--out", required=True)
    sr.add_argument("--new-only", action="store_true")
    sr.add_argument("--run-date")
    ms = sub.add_parser("mark-sheet")
    ms.add_argument("--run-date")
    a = p.parse_args()
    {"add": cmd_add, "show": cmd_show, "approve": cmd_approve, "next": cmd_next, "mark": cmd_mark,
     "sheet-rows": cmd_sheet_rows, "mark-sheet": cmd_mark_sheet}[a.cmd](a)


if __name__ == "__main__":
    main()
