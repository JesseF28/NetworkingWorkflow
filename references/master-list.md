# Stages 3 and 5: Add to the master list

The master list is the Google Sheet **Vanderbilt networking tracker** (`tracker_sheet_id` in config). Four records work together:

| Record | Holds | Written |
|---|---|---|
| Weekly Google Doc | The list, for Jesse to read | Stage 3 |
| `prospect_log_csv` | Everyone ever listed, so repeats get blocked | Stage 3 |
| `outbox_json` | Every email and its send status, between sessions | Stages 3 and 4 |
| Tracker sheet, "Weekly prospects" tab | Each week's people and send status | Stages 3 and 5 |

The sheet's main **Tracker** and **Activity** tabs are for real correspondence (sent, replied, call booked), so don't write listed-but-unsent people there.

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

## Stage 3d: Add to the sheet

This needs the **Google Sheets connector**, connected 2026-11-05 (load `get_spreadsheet`, `get_values`, `append_values`, `update_values` and `update_spreadsheet` with ToolSearch). Read `anthropic-skills:google-workspace` and its `references/sheets.md` first, because Sheets parses input like the UI does and can turn text into dates or numbers.

```
python -I scripts/outbox.py sheet-rows --new-only --out <scratch>/rows.json
```
1. Read the sheet's tabs. If "Weekly prospects" doesn't exist, add it with `columns` from `rows.json` as the header in row 1. Keep the header `Name` exactly: `dnc.py` finds people through it, so this tab also feeds the do-not-contact list.
2. Read the Email column, drop any row whose address is already there, and append the rest.
3. Read the tab again and check the rows landed, then run `python -I scripts/outbox.py mark-sheet`.

**If the connector isn't available**, don't edit the sheet through Chrome. The rows stay unmarked in the outbox, so nothing is lost and the next run with the connector adds them all through `--new-only`. The log and weekly docs still prevent repeats. Say in your final message that the sheet wasn't updated.

## Stage 5: After scheduling

1. Run `python -I scripts/outbox.py sheet-rows --out <scratch>/rows.json`, which has every person's current send status.
2. On "Weekly prospects", find each person's row by email and update the Send status cell, for example `Scheduled 2026-11-12 13:00 ET`. Add a row for anyone missing, such as a one-person send.
3. Read the cells back to check them, then run `mark-sheet`.

Without the connector, skip this and say so. The outbox keeps the status, so it can be caught up later.
