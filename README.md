# NetworkingWorkflow

One Claude skill that goes from finding people to making emails to schedule sending them. It replaces `weekly-networking-prospects`, `vanderbilt-outreach` and `networking-sent-sync`.

```
Find people → Write emails → Add to master list → Schedule send → Update master list → Sync sent mail
```

## How to use it

| Say this | What happens |
|---|---|
| "Build this week's networking list" | Finds 20 people, writes their emails and adds them to the list, without sending anything |
| "Send this week's emails" | Asks when you're free for calls, then schedules anything still waiting |
| "Send just the verified ones" | Schedules only people whose address was confirmed |
| "Do the whole thing" | Runs everything straight through to scheduling |
| Paste a brief or notes about one person | Writes and schedules that one email |
| "What's queued?" | Shows every email and its status |
| "Update the tracker from my sent mail" | Moves everyone you emailed from Prospects to Contacted |

The Tuesday 10 a.m. scheduled run finds people, writes the emails and releases them, then stops and asks when you're free for calls. **Before anything is scheduled, the skill always asks for your availability** and puts those times into every email. Once you answer, emails that pass the automatic checks are scheduled, including guessed addresses. To stop one, cancel it in Outlook before Thursday.

The Sunday 6 a.m. scheduled run syncs your sent mail into the Master Tracker.

Emails go out on **Thursdays at 1 PM Eastern**. Anything scheduled after Thursday morning goes the following Thursday. To change the day or time, edit `send_day` and `send_time_eastern` in `config.json`.

Every step runs one after another, and a step only starts once the last one passes its check.

## What's in here

| Path | Purpose |
|---|---|
| `SKILL.md` | The workflow: what runs when, the checks before sending, the one-person path |
| `config.json` | IDs, file paths, your availability line, search rules |
| `references/find-people.md` | Stage 1: do-not-contact list, criteria, finding emails |
| `references/sources.md` | What worked and failed on PitchBook, LinkedIn, AUM13F and others |
| `references/email-template.md` | Your email template and real examples |
| `references/master-list.md` | Stages 3 and 5: doc, log, outbox, Master Tracker |
| `references/schedule-send.md` | Stage 4: Outlook steps and lessons from past runs |
| `references/sent-sync.md` | Stage 6: matching Sent Items to the Master Tracker |
| `references/dashboard.md` | Stage 7: Dashboard tab and call log |
| `references/weekly-calls.md` | Stage 8: Sunday noon schedule of the week's calls, with prep |
| `scripts/dnc.py` | Builds and checks the do-not-contact list |
| `scripts/build_doc.py` | Validates the list, builds the Google Doc, writes the log |
| `scripts/outbox.py` | Tracks each email from written to scheduled |
| `scripts/sent_sync.py`, `scripts/read_sent_items.js` | Read Sent Items and plan the tracker changes |
| `scripts/check_pronouns.py` | Flags unsourced pronouns in the call schedule draft |
| `tests/` | Tests for the outbox: `python -m unittest discover -s tests` |

Prospect data (the log, pool, AUM cache, outbox and sync state) stays in `OneDrive/Documents/NetworkingCalls` and is deliberately not in this repo.

## Install on a new computer

```bash
git clone https://github.com/JesseF28/NetworkingWorkflow ~/.claude/skills/networking-workflow
```

The clone is the installed skill, so `git pull` updates it. Paths in `config.json` are specific to this computer.

## What it needs

- **Claude in Chrome**, signed in to Vanderbilt Outlook, for scheduling. PitchBook runs there too, when available; it's recommended but optional, and the skill falls back to other sources without it.
- **Google Drive connector** for the weekly doc and reading the Master Tracker.
- **Google Sheets connector** to write to the Master Tracker. Without it, everything else works and the rows wait in the outbox.
