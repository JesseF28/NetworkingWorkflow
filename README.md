# NetworkingWorkflow

One Claude skill that goes from finding people to making emails to schedule sending them. It replaces `weekly-networking-prospects` and `vanderbilt-outreach`.

```
Find people → Write emails → Add to master list → You approve → Schedule send → Update master list
```

## How to use it

| Say this | What happens |
|---|---|
| "Build this week's networking list" | Finds 20 people, writes their emails, adds them to the list, then stops for your approval |
| "Send this week's emails" | Shows who's waiting, then schedules the ones you approve |
| "Send just the verified ones" | Schedules only people whose address was confirmed |
| "Do the whole thing" | Runs everything, pausing once for your approval |
| Paste a brief or notes about one person | Writes and schedules that one email |
| "What's queued?" | Shows every email and its status |

The Tuesday 10 a.m. scheduled run does the first row automatically. **Nothing is ever scheduled without your approval in chat.**

## What's in here

| Path | Purpose |
|---|---|
| `SKILL.md` | The workflow: what runs when, the approval step, the one-person path |
| `config.json` | IDs, file paths, your availability line, search rules |
| `references/find-people.md` | Stage 1: do-not-contact list, criteria, finding emails |
| `references/sources.md` | What worked and failed on PitchBook, LinkedIn, AUM13F and others |
| `references/email-template.md` | Your email template and real examples |
| `references/master-list.md` | Stages 3 and 5: doc, log, outbox, tracker sheet |
| `references/schedule-send.md` | Stage 4: Outlook steps and lessons from past runs |
| `scripts/dnc.py` | Builds and checks the do-not-contact list |
| `scripts/build_doc.py` | Validates the list, builds the Google Doc, writes the log |
| `scripts/outbox.py` | Tracks each email from "needs approval" to "scheduled" |
| `tests/` | Tests for the outbox: `python -m unittest discover -s tests` |

Prospect data (the log, pool, AUM cache and outbox) stays in `OneDrive/Documents/NetworkingCalls` and is deliberately not in this repo.

## Install on a new computer

```bash
git clone https://github.com/JesseF28/NetworkingWorkflow ~/.claude/skills/networking-workflow
```

The clone is the installed skill, so `git pull` updates it. Paths in `config.json` are specific to this computer.

## What it needs

- **Claude in Chrome**, signed in to Vanderbilt Outlook, for scheduling. PitchBook runs there too.
- **Google Drive connector** for the weekly doc and reading the tracker.
- **Google Sheets connector** to write to the tracker. Without it, everything else works and the rows wait in the outbox.
