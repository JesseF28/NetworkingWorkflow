# Stage 4: Schedule send

This stage puts real email in front of real people, so it only runs for people in `approved` status, and only in a conversation with Jesse (see Approval in SKILL.md). The October 18 run scheduled 15 emails this way. Its problems are written in here because each one cost time or nearly sent something wrong.

## Before the first email

**1. Get the attachment ready.** Find the exact `Fagen.pdf`: a copy Jesse supplied for this request, otherwise `attachment_path` in config, then the current workspace and accessible user files. Confirm it's a readable PDF. If it's missing or several plausible copies remain, ask Jesse which one.

Copy it into your scratchpad directory and upload from there. Chrome's `file_upload` refuses files outside the folders the session can read, and `Downloads` was refused in October. Keep the filename `Fagen.pdf`.

**2. Open Outlook in Claude in Chrome.** Read `anthropic-skills:chrome-browser` first. Chrome is the browser with both the signed-in Vanderbilt mailbox and a file upload tool. Open `outlook_mail_url` if needed.

Verify the mailbox and the compose **From** address are both `sender_mailbox`, ignoring case. A connected personal Outlook account is never a fallback, and browser sign-in is separate from connector sign-in. If Vanderbilt isn't available, ask Jesse to sign in. Never type a password.

**3. Work out the delivery time.** The default is 12:00 PM Eastern (`send_time_eastern`) on the next calendar day in `America/New_York`, weekends included. Honor a different date or time Jesse asks for. Confirm the timezone from the schedule dialog or mailbox settings. If Outlook uses another timezone, convert. Jesse is often in Central time, where noon Eastern shows as 11:00 AM. If you can't verify the timezone, save drafts instead of scheduling and explain why.

**4. Check for duplicates once, for the whole batch.** Look through Drafts and Sent Items for the approved addresses (`references/sources.md` has a fast way to read the list).
- A matching Vanderbilt draft: reuse it, and keep one copy of the attachment.
- Already correctly scheduled from Vanderbilt: `outbox.py mark` it as scheduled, report it, and move on.
- Queued from another account: Jesse must authorize and confirm cancelling that copy first. Until then, save the Vanderbilt message as a draft.
- Already sent: mark it `skipped` with a note, and tell Jesse.

## For each email, one at a time

Get the next one with `python -I scripts/outbox.py next`. Use its subject and body exactly. Don't rewrite them from memory.

1. **Compose.** Start a new mail. Enter To, Subject and body. Press Return after typing the address and confirm it resolved to a recipient chip.
2. **Attach.** Use `find` for the composer's file input, then `file_upload` with the scratchpad copy.
3. **Verify in the composer before scheduling:** From, To, subject, body, and exactly one `Fagen.pdf` that has finished uploading.
4. **Schedule.** Open **More send options** (the arrow beside Send), then **Schedule send**. The first time, choose **Custom time** and enter the date and time. After that the dialog usually offers the last chosen time as a preset, which is faster, but read it before picking it. Commit only through the dialog's Send button.
5. **Confirm and record.** Wait for the composer to close, then:
   ```
   python -I scripts/outbox.py mark --email <address> --status scheduled --scheduled-for "2026-11-11 12:00 ET"
   ```
   Mark each email as you finish it, so an interrupted run picks up where it stopped.

Group steps with `browser_batch`, but take a fresh screenshot or `find` before each step that commits something. Coordinates go stale when Outlook redraws. For a draft-only request, stop after step 3, save it, and mark it `draft_saved`.

## What went wrong in October

- **Laggy clicks.** Outlook is slow to redraw, and a click on a scheduled message un-scheduled it, turning it back into a draft. Wait for the page to settle, and don't click scheduled messages in Drafts unless you mean to change them.
- **Stray reply drafts.** Clicks landing on the reading pane created reply drafts. Check that a new compose window is open before typing or attaching. Discard any strays you made, and only those.
- **Adding an attachment later** means cancelling the send, attaching, and rescheduling. Attaching before the first schedule avoids all of that.

## If the result is ambiguous

If scheduling times out or you can't tell what happened, look at the message in Outlook, including Drafts. Mark it `unclear` if you still can't tell, and leave it: `next` won't offer it again. Only retry when Outlook positively shows the same message is unscheduled:
```
python -I scripts/outbox.py mark --email <address> --status approved --note "Outlook shows it unscheduled in Drafts"
```
A duplicate cold email can't be taken back, so an unclear result is always better than a second send.

## Final check, after the last email

1. Look through Drafts and confirm every message marked `scheduled` shows its delivery date and time and the attachment. Read the list; don't click into the messages. Anything that fell back to a plain draft goes back to `approved` with a note, and gets rescheduled.
2. Look in Sent Items and confirm nothing went out early.
3. Run `python -I scripts/outbox.py show` and make sure it matches what you saw.
4. Delete your scratchpad copy of the PDF, then go to stage 5 in `references/master-list.md`.

Report each outcome with the sender, recipient, subject, attachment and Eastern delivery time, and keep verified schedules separate from saved drafts.
