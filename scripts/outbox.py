"""The outbox: every written email, from "needs approval" through "scheduled".

It carries a run's emails between sessions (the Tuesday run writes them, a later
chat can schedule them), makes sure nothing is scheduled until it's released,
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
  python -I outbox.py availability (--text "Would you be open to ..." | --keep) [--save-config] [--run-date D]
  python -I outbox.py next
  python -I outbox.py when
  python -I outbox.py mark --email x@y.com --status scheduled --scheduled-for "2026-11-12 13:00 ET" [--note N]
  python -I outbox.py sheet-rows --out rows.json [--new-only] [--run-date D]
  python -I outbox.py mark-sheet [--run-date D]
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import zoneinfo
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
    CFG = json.load(f)

# Where each status may go next. Release only happens through the `approve` command,
# which the skill runs itself once a list has passed its checks.
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
# The Master Tracker's Prospects tab, in order. sent_sync.py stops if these columns move.
SHEET_COLUMNS = ["Contact", "Firm", "Stage", "Next action", "Email", "Email confidence", "Role / focus",
                 "Vanderbilt class", "Location", "Last touch", "Target date (source)", "AUM / evidence",
                 "Notes & history", "Sources"]
SHEET_STAGE = {"needs_approval": "Draft saved", "approved": "Draft saved", "draft_saved": "Draft saved",
               "scheduled": "Scheduled — confirm sent", "unclear": "Hold", "failed": "Hold", "skipped": "Hold"}
NEXT_ACTION = {
    "needs_approval": "Waiting to be scheduled for Thursday 1 PM Eastern.",
    "approved": "Waiting to be scheduled in Outlook.",
    "draft_saved": "Draft saved in Outlook; finish and schedule it.",
    "scheduled": "Sunday sync confirms it was sent.",
    "unclear": "Check Outlook: it's unclear whether this was scheduled.",
    "failed": "Scheduling failed; try again or find another address.",
    "skipped": "Skipped; don't email unless Jesse asks.",
}


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
    print(f"{added} added to {a.outbox}, waiting to be released.")


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


OPEN = {"needs_approval", "approved", "draft_saved", "unclear", "failed"}
AVAILABILITY_START = "Would you be open to"


def with_availability(body, line):
    """Swap the availability paragraph (the one that starts "Would you be open to") for `line`."""
    paras = body.split("\n\n")
    hits = [n for n, p in enumerate(paras) if p.strip().startswith(AVAILABILITY_START)]
    if len(hits) != 1:
        return None
    paras[hits[0]] = line
    return "\n\n".join(paras)


def cmd_availability(a):
    """Record the call times Jesse confirmed for this batch, and put them in every open email."""
    line = (a.text or CFG["availability"]).strip()
    if not line.startswith(AVAILABILITY_START):
        fail(f'the availability line should start "{AVAILABILITY_START}", like the template')
    items = load(a.outbox)
    chosen = [i for i in selected(items, a) if i["status"] in OPEN]
    if not chosen:
        fail("no open emails to update")
    today = dt.date.today().isoformat()
    for i in chosen:
        body = with_availability(i["body"], line)
        if body is None:
            fail(f"{i['name']}: couldn't find exactly one paragraph starting \"{AVAILABILITY_START}\"; fix the body first")
        i["body"], i["availability_confirmed"] = body, today
        i["history"].append({"on": today, "status": i["status"], "note": "availability confirmed with Jesse"})
    save(a.outbox, items)
    if a.save_config and a.text:
        path = os.path.join(HERE, "config.json")
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["availability"] = line
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print("Saved as the default availability in config.json.")
    print(f"Availability confirmed for {len(chosen)}: {', '.join(i['name'] for i in chosen)}")


def cmd_next(a):
    waiting = [i for i in load(a.outbox) if i["status"] == "approved"]
    if not waiting:
        print("Nothing approved is waiting.")
        return
    unconfirmed = [i for i in waiting if not i.get("availability_confirmed")]
    if unconfirmed:
        fail(f"{len(unconfirmed)} approved emails don't have confirmed call times yet "
             f"({', '.join(i['name'] for i in unconfirmed)}). Ask Jesse when they're available, then run "
             "`outbox.py availability --text \"...\"` (or `--keep` if the current times still work).")
    i = waiting[0]
    print(f"{len(waiting)} approved and waiting. Next:")
    print(json.dumps({k: i.get(k) for k in ("name", "firm", "email", "email_confidence", "subject", "body")},
                     indent=1, ensure_ascii=False))


def next_send_slot(now):
    """The next send day and time that leaves enough lead time to finish a batch. `now` is Eastern."""
    day = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].index(CFG["send_day"])
    hour, minute = (int(x) for x in CFG["send_time_eastern"].split(":"))
    slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + dt.timedelta(days=(day - now.weekday()) % 7)
    if slot - now < dt.timedelta(minutes=CFG["send_lead_minutes"]):
        slot += dt.timedelta(days=7)
    return slot


def cmd_when(a):
    eastern = zoneinfo.ZoneInfo("America/New_York")
    now = dt.datetime.fromisoformat(a.now).replace(tzinfo=eastern) if a.now else dt.datetime.now(eastern)
    slot = next_send_slot(now)
    central = slot.astimezone(zoneinfo.ZoneInfo("America/Chicago"))
    print(f"Send at: {slot.strftime('%A, %B')} {slot.day}, {slot.year}, {slot.strftime('%I:%M %p').lstrip('0')} Eastern")
    print(f"In Central time: {central.strftime('%I:%M %p').lstrip('0')}")
    print(f"For outbox.py mark: {slot.strftime('%Y-%m-%d %H:%M')} ET")


def cmd_mark(a):
    items = load(a.outbox)
    found = [i for i in items if key(i["email"]) == key(a.email)]
    if not found:
        fail(f"{a.email} is not in the outbox")
    i = found[0]
    old = i["status"]
    if a.status not in MOVES[old]:
        fail(f"{i['name']} is '{old}' and can't move to '{a.status}'"
             + ("; release it with `approve` first" if old == "needs_approval" else ""))
    if (old, a.status) in NOTE_REQUIRED and not a.note:
        fail(f"moving {i['name']} from '{old}' back to 'approved' needs --note saying what Outlook showed")
    if a.status == "scheduled" and not a.scheduled_for:
        fail("--scheduled-for is required, as read back from Outlook")
    i["status"] = a.status
    i["scheduled_for"] = a.scheduled_for if a.status == "scheduled" else None
    i["history"].append({"on": dt.date.today().isoformat(), "status": a.status, "note": a.note})
    save(a.outbox, items)
    print(f"{i['name']}: {old} -> {a.status}")


def as_text(value):
    """The apostrophe stops Sheets turning class years and dates into numbers."""
    return f"'{value}" if value not in (None, "") else ""


def target_date(i):
    if not i.get("scheduled_for"):
        return ""
    d = dt.date.fromisoformat(i["scheduled_for"][:10])
    return as_text(f"{d.strftime('%b')} {d.day}, {d.year}")


def sheet_row(i):
    aum = i.get("aum_musd", "")
    evidence = "; ".join(x for x in (f"{aum} million" if aum not in ("", None) else "", i.get("aum_source", "")) if x)
    notes = [f"Weekly list {i['run_date']}", f"Subject: {i['subject']}"]
    notes += [f"Vanderbilt: {i['vanderbilt']}"] if i.get("vanderbilt") else []
    notes += [f"Class source: {i['grad_year_source']}"] if i.get("grad_year_source") else []
    sources = [i.get(k) for k in ("doc_url", "profile_source", "aum_source") if i.get(k)]
    return [i["name"], i.get("firm", ""), SHEET_STAGE[i["status"]], NEXT_ACTION[i["status"]], i["email"],
            i.get("email_confidence", ""), " / ".join(x for x in (i.get("title"), i.get("strategy")) if x),
            as_text(i.get("grad_year")), i.get("location", ""), "", target_date(i), evidence,
            "\n".join(notes), "\n".join(sources)]


def cmd_sheet_rows(a):
    rows = [sheet_row(i) for i in selected(load(a.outbox), a) if not (a.new_only and i.get("on_sheet"))]
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
    sys.stdout.reconfigure(encoding="utf-8")  # Windows defaults to cp1252, which garbles the en dash in "15–20"
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
    av = sub.add_parser("availability")
    line = av.add_mutually_exclusive_group(required=True)
    line.add_argument("--text", help="the full availability paragraph Jesse confirmed")
    line.add_argument("--keep", action="store_true", help="Jesse confirmed the current line in config.json")
    av.add_argument("--save-config", action="store_true", help="also make --text the default in config.json")
    av.add_argument("--run-date")
    sub.add_parser("next")
    wh = sub.add_parser("when")
    wh.add_argument("--now", help="Eastern time to calculate from, for testing, e.g. 2026-11-12T09:00")
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
    {"add": cmd_add, "show": cmd_show, "approve": cmd_approve, "availability": cmd_availability, "next": cmd_next,
     "when": cmd_when, "mark": cmd_mark,
     "sheet-rows": cmd_sheet_rows, "mark-sheet": cmd_mark_sheet}[a.cmd](a)


if __name__ == "__main__":
    main()
