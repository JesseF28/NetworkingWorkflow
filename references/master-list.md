# Stages 3 and 5: Add to the master list

The master list is the Google Sheet **Vanderbilt Networking — Master Tracker** (`tracker_sheet_id` in config). Its **Prospects** tab holds people who haven't been emailed, and **Contacted** holds people who have. Each person moves through it like this:

| When | Where they are | Stage |
|---|---|---|
| Stage 3, listed | Prospects | `Draft saved` |
| Stage 5, scheduled | Prospects | `Scheduled — confirm sent` |
| Stage 6, seen in Sent Items | Contacted | `Initial email sent`, then later stages |

Only stage 6 moves people to Contacted, because only Sent Items proves an email went out. Don't add anyone to Contacted here.

Four records work together:

| Record | Holds | Written |
|---|---|---|
| Weekly Google Doc | The list, for Jesse to read | Stage 3 |
| `prospect_log_csv` | Everyone ever listed, so repeats get blocked | Stage 3 |
| `outbox_json` | Every email and its send status, between sessions | Stages 3 and 4 |
| Master Tracker | Where every person stands | Stages 3, 5 and 6 |

## Stage 3a: Validate

Put the finished prospects in `<scratch>/prospects.json` (field list at the top of `scripts/build_doc.py`), then:
```
python -I scripts/build_doc.py validate --prospects <scratch>/prospects.json --dnc <scratch>/dnc.json
```
It checks: exactly 20, everyone in the class of 2020–2026 with a source for the year, nothing on the do-not-contact list, no duplicates, every person has an email and confidence label, AUM under $2.5B with a source, at most 2 per firm, the availability line is present, and the greeting uses the right first name. Fix what it reports and re-run until it passes. Don't upload a list that fails. Fewer than 20 strong people is better than padding: if you truly can't reach 20, pass `--allow-short` and say why at the top of the doc.

## Stage 3b: Build and upload the doc

```
python -I scripts/build_doc.py html --prospects <scratch>/prospects.json --out <scratch>/doc.html --week-of <YYYY-MM-DD> --notes "<run notes>"
```
Run notes are 1–3 short lines, such as "PitchBook was signed out; emails came from firm sites and patterns." Leave them empty if nothing went wrong. `--week-of` is the date of the run. Use the same date in the title, the log and the outbox.

Upload with Drive `create_file`: `title` = `Networking prospects — week of <Mon D, YYYY>`, `parentId` = `drive_folder_id`, `contentMimeType` = `text/html`, `textContent` = the HTML. Drive converts it to a Google Doc. Open it with `read_file_content` and check that everyone came through.

## Stage 3c: Log and queue

Only after the upload succeeds:
```
python -I scripts/build_doc.py log --prospects <scratch>/prospects.json --log <prospect_log_csv> --doc-url <viewUrl> --week-of <YYYY-MM-DD>
python -I scripts/outbox.py add --prospects <scratch>/prospects.json --run-date <YYYY-MM-DD> --doc-url <viewUrl>
```
Always log through the script. It labels the week, and if Excel has the log open it saves the rows to a `prospect-log-pending-<date>.csv` beside it, which the next run merges. Those people still count as contacted. If that happens, tell Jesse.

The outbox matters as much as the log: scratch folders disappear when a session ends, and the outbox is how a later chat gets the emails without rewriting them.

## Stage 3d: Add to the Master Tracker

This needs the **Google Sheets connector** (load `get_spreadsheet`, `get_values`, `append_values` and `update_values` with ToolSearch). Read `anthropic-skills:google-workspace` and its `references/sheets.md` first, because Sheets parses input like the UI does and can turn text into dates or numbers.

```
python -I scripts/outbox.py sheet-rows --new-only --out <scratch>/rows.json
```
The rows already match the tab's 14 columns, and class years and dates carry the apostrophe that keeps them as text. Don't change the columns: stage 6 stops if they move.

1. Read the Email column (E) of both `Prospects` and `Contacted`, and drop any row whose address is already on either tab.
2. Append the rest to `Prospects`.
3. Read the tab back and check the rows landed, then run `python -I scripts/outbox.py mark-sheet`.

**If the connector isn't available**, don't edit the sheet through Chrome. The rows stay unmarked in the outbox, so nothing is lost and the next run with the connector adds them all through `--new-only`. The log and weekly docs still prevent repeats. Say in your final message that the sheet wasn't updated.

## Stage 5: After scheduling

1. Run `python -I scripts/outbox.py sheet-rows --out <scratch>/rows.json`, which has every person's current Stage, Next action and Target date.
2. On `Prospects`, find each person's row by email and update columns C (Stage), D (Next action) and K (Target date) from their row in `rows.json`. If someone isn't there, such as a one-person send, append their whole row.
3. If a person is already on `Contacted`, leave that row alone. It's further along.
4. Read the cells back to check them, then run `mark-sheet`.

Without the connector, skip this and say so. The outbox keeps the status, so it can be caught up later.
