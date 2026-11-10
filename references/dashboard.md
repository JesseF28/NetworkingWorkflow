# Stage 7: Dashboard and call log

The "Dashboard" tab on the Master Tracker (right after Prospects) shows how outreach is going and what Jesse should do next. It is all live formulas over the Contacted tab and the call log, so it never needs rebuilding. This stage keeps its inputs right: the call log and the auto-reply list.

## What's on it

| Rows | Section | Source |
|---|---|---|
| 4–12 | Scorecard: emailed, delivered, replies, calls booked and completed, bounced, follow-ups due, replies waiting | Contacted |
| 4–12, column E | Auto-replies to leave out (yellow cells Jesse types names into) | Jesse |
| 14–61 | Six charts: funnel, emails and replies by week, replies by strategy, class and firm size, bounces by address type | Data columns |
| 62–143 | Do this next, most urgent first (up to 80 rows) | Contacted + call log promises |
| 146–187 | Summer internship list: Hot, Warm, Worth another try (up to 40 rows) | Contacted + call log |
| 190 on | Call log, one row per conversation or follow-up; header on row 192, entries from row 193 | Jesse and this stage |
| Columns U–BX | Data the lists and charts read. Formulas only; never type there | Formulas |

Rates show as "3 of 12", and reply rates leave out bounced emails. "Hot" comes only from the call log's Internship signal column; "Warm" is anyone who replied; "Worth another try" is an investing role with no reply after 21+ days.

## Rules

- Never add, remove or reorder columns on Contacted or Prospects. `sent_sync.py` stops when they change, and the dashboard reads Contacted by column letter (A Contact, B Firm, C Stage, D Next action, F Email confidence, G Role / focus, H Vanderbilt class, J Last touch, L AUM, M Notes).
- Last touch stays text like "Oct 19, 2026"; the dashboard turns it into a date. The first-email date comes from the "Sent Items sync" lines in Notes, so keep that format.
- Call log headers say "Person", not "Contact" or "Name", so `dnc.py` doesn't pick up section titles as names. Keep it that way.
- Add call log rows at the bottom of the log, never between sections above it. Write the date as a real date (`10/13/2026`), and Reconnect as a month (`Jan 2027`).
- To change a formula, test it on a copy of the sheet first, and compare the scorecard against a separate count (Python over a downloaded .xlsx) before touching the real tab.

## After a call

When Jesse shares a recording, transcript, brief or notes from a conversation (the `coffee-chat-transcriber` skill makes the summary), add one call log row: Date, Person (exactly as on Contacted), Firm, Topics, Best advice, What they offered, What Jesse promised, Done? (blank), Internship signal (Hot if they offered help or an intro, Warm otherwise), Reconnect (default Jan 2027), and the transcript or notes location. Promises with Done? blank show up in Do this next until Jesse marks them Yes.

## Sunday sync additions

After stage 6 writes the sheet:

1. For each person whose new Sent Items lines include a second outreach email to them with no reply in between (a follow-up, not a thank-you or calendar item), add a call log row: Date of the follow-up, Person, Firm, Topics "Follow-up email: <subject>", everything else blank.
2. For each person moved to Reply received this week, the reply may be an out-of-office. If Jesse confirms one is, put their name in the auto-reply cells (Dashboard E5:E12). Don't decide this yourself from the outside-sender tag.
3. Read back Dashboard B5:B12 and report the scorecard in the Sunday summary.
