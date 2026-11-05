# Research sources

These notes reflect what worked and what failed in real runs. Update them when you learn something new.

## PitchBook (best for people + emails)

Jesse has PitchBook through Vanderbilt (account `jesse.r.fagan@vanderbilt.edu`). Use it in Chrome (Claude in Chrome tools: load them in one ToolSearch call; see `anthropic-skills:chrome-browser`).

- Open `https://my.pitchbook.com/`. If you land on the Morningstar/PitchBook sign-in page, Jesse has said you may start the sign-in (2026-11-05):
  1. Enter `jesse.r.fagan@vanderbilt.edu` and click Continue.
  2. If the flow goes straight to a push prompt (Duo or similar), wait for Jesse to approve it on their phone. Check the page about every 30 seconds for up to 5 minutes. If `PushNotification` is available, send one saying the approval is waiting.
  3. If a password field appears, stop there. Never type a password, even if one is saved or Jesse has approved sign-in in general. Only Jesse enters it.
  4. If the push isn't approved in time, or a password is needed, carry on with public sources and put "PitchBook was signed out" in the run notes and your final reply.
- **People search (the fast path).** Jesse already has a People Screener search: University = Vanderbilt, Include Active Positions, Location = United States > New York Metro (~690 people). Open it from Search Tools → Recent Searches (the "Person" row; the date link opens the results), or go straight to `https://my.pitchbook.com/search-results/s679995279/persons`. The table shows position, company, **email**, location and the full biography for every person, 25 per page (25 is the maximum).
  - Read it with `javascript_tool`. Each person is a `.data-table__row` element with 18 child cells, in this order: first, last, position, company, board seats, roles, deal roles, phone, **email (8)**, **location (9)**, address fields, **bio (17)**. Rows of the frozen name column have fewer cells, so skip them.
  - To read all pages, start an async loop that stores rows in a `window.__…` variable, clicks the button whose text is `Next`, and waits until the first row changes. Don't `await` the loop inside the tool call: it takes ~10 s per page and the call times out after 45 s. Start it, then poll the variable. Wait until rows exist before starting, or the loop ends on page 1.
  - Filter in the page before returning anything: drop lawyers (`J.D.`, "practice focuses", Counsel), keep investing roles, and keep rows whose bio shows a Vanderbilt **bachelor's** degree (B.A./B.S./B.E./Bachelor), not only an MBA/Owen, M.A. or Master of Accountancy.
  - `javascript_tool` output is cut at about 1,000 characters, and strings that look like query strings are blocked. To read a long result, put it in a temporary `<article>` element at the top of `document.body` and call `get_page_text`, which reads `<article>` first.
  - On 2026-11-01/02 a full pass gave 693 → 384 investing-type → ~199 with a Vanderbilt bachelor's in the bio. After AUM checks only ~13–21 qualified, and 12 were used in week 1. Everyone else is in `prospect-pool.csv` or was ruled out (see `firm-aum-cache.csv`), so **this saved search is nearly exhausted**. Don't repeat the bio-based pass.
  - A gap worth closing: the 384 → 199 step kept only people whose *bio text* mentions a Vanderbilt bachelor's. People whose bio doesn't mention their degree were dropped even if their PitchBook Education field shows a Vanderbilt BA. Use **Edit table** to add the Education column (or open each profile's Education section) and re-screen those ~185 at small firms.
- **Grad year (2020–2026 rule, since 2026-11-05).** Read the year from the Education section of the person's profile or the Education column, for example `Vanderbilt University, BA (Bachelor of Arts), 2003, Economics`. Bios rarely state it. Look for a graduation-year filter in the Screener's education criteria and use it if it exists; otherwise filter on the Education column in the page. Recent grads often have short bios or no PitchBook profile, so also search LinkedIn with WebSearch (`allowed_domains: ["linkedin.com"]`) using terms like `"Vanderbilt University" 2022 analyst private equity`, and look through associate and analyst listings on team pages of small firms.
- **Best search for the 2020–2026 rule (found 2026-11-05).** In the People Screener criteria, set University = Vanderbilt, Position Levels = Analyst + Associate, and no location. That returned 159 people nationwide, 134 of them in the US and not lawyers, versus 693 for New York alone. Add the University/Institution column with Edit table; the rows then have 18 cells: university (0), first (1), last (2), position (3), company (4), email (8), location (9), state (13), country (15), bio (17). Run AUM checks on these firms first. PitchBook's Education section often has **no year**, so get years from LinkedIn (WebSearch with `allowed_domains: ["linkedin.com"]`, quoting the name, firm and "Vanderbilt University"). The snippets often show dates like 2018–2022. Associates at funds under $2.5B are the sweet spot.
- **Nationwide search (since 2026-11-02).** Jesse widened the search to anywhere in the US. In the People Screener, use Modify Criteria to change Location from New York Metro to United States, and exclude New York Metro, since that's already been worked through. Add the Education column with Edit table so undergrad degrees can be read without the bio. Expect the same funnel: most hits are at big firms, so check the firm AUM cache before doing anything else.
- **Sessions expire.** PitchBook signed Jesse out about a day after sign-in (2026-11-01 → 11-02), so expect a scheduled run to find it signed out unless Jesse signs in that morning or the night before.
- **Single lookups**: the "Search PitchBook…" box at the top finds a person or firm. The first suggestion opens the profile; an investor profile shows AUM in General Information.
- PitchBook-listed emails count as `Verified (PitchBook)`, and the person's profile URL (from the name link) is the `profile_source`.
- **Firm AUM**: the investor profile's AUM field. Label it "PitchBook AUM".
- **Emails**: person profiles often list a work email. The tracker sheet's "PE HF RE additions" tab shows earlier PitchBook-sourced emails and how they were recorded (profile URL as the source).
- Read pages with `get_page_text` instead of screenshots where you can. It is faster and cheaper.

## Finding Vanderbilt alumni without PitchBook

What worked:
- **WebSearch with `allowed_domains: ["linkedin.com"]`**. Unlike plain WebSearch, it returns real `linkedin.com/in/...` URLs, and the snippets read like "Experience: X · Education: Vanderbilt University · Location: New York". Query ideas:
  - `"Vanderbilt University" "private equity" associate New York`
  - `"Vanderbilt University" "Capital Partners" Connecticut`
  - `"Vanderbilt University" venture capital associate New York`
  - `"Vanderbilt University" hedge fund analyst New York`
  - Vary by title (analyst, associate, vice president, principal) and by state.
- **Firm team pages.** Search the page source for "Vanderbilt" instead of reading the visible text. Many sites keep full bios and `mailto:` links in HTML attributes (e.g. `data-member-*`), which `get_page_text` and WebFetch miss. In Chrome, run something like this with `javascript_tool`:
  ```js
  const h = document.documentElement.innerHTML;
  [...h.matchAll(/.{0,300}Vanderbilt.{0,300}/g)].map(m => m[0].replace(/<[^>]+>/g, ' ')).slice(0, 10)
  ```
  Then do the same for `@<firm-domain>` to find emails.

What didn't work:
- Plain WebSearch without the domain filter mostly returns marketscreener and other aggregators.
- Google search in Chrome works for about 20 queries and then shows an "unusual traffic" CAPTCHA that stays up. Bing returned nothing and DuckDuckGo blocked. Don't solve CAPTCHAs. Use a few Chrome Google searches at most, and only after WebSearch.

Filtering candidates:
- Most LinkedIn hits are at big firms (Blackstone, Vista, EQT, HIG, Sentinel…) or are bankers. Check the firm AUM cache first.
- **Owen MBA false positives** are common. Drop anyone whose Vanderbilt entry is an MBA or who lists another undergraduate school.
- **Stale roles**: confirm the person on the firm's current team page. LinkedIn snippets lag job changes.

## AUM13F.com (AUM check)

Public site with each SEC-registered adviser's regulatory AUM from Form ADV. Guessing firm-page slugs (`/firm/<slug>`) usually returns 404/410, and `/search?q=` doesn't exist. What works is the site's own search, called from an open aum13f.com page in Chrome with `javascript_tool`:
```js
const firms = ["Long Ridge Equity", "Balance Point Capital", "BlackBarn"];
const out = {};
for (const f of firms) {
  const r = await fetch(url_d.search, {method: "POST", headers: {"Content-Type": "application/x-www-form-urlencoded"}, body: "keyword=" + encodeURIComponent(f)});
  out[f] = (await r.json()).slice(0, 3).map(x => [x.label, x.aum_disp, x.url]);
}
out
```
`url_d.search` is a variable the page defines, not a literal path: posting to `"/url_d.search"` returns an HTML error page. This checks about 30 firms in one call; return the results through a temporary `<article>` + `get_page_text` (see the PitchBook section), because the tool cuts long output. Each result has `label`, `aum_disp`, `url` and `rtype` (`Firm`, `Fund` or `Person`). Use the `Firm` row; if there are only `Fund` rows, sum their values.

- On a firm page, the "Website" link is JavaScript (`click_js('https://…')`). Read the URL from the element's `onclick` attribute. This is the most reliable way to get the firm's real email domain.
- **Exempt reporting advisers** (most VC firms) show no firm AUM, only each fund's gross asset value. Sum the funds and record it as e.g. `95` with the AUM source as the AUM13F page; mention "sum of fund GAVs" in the profile notes.
- If whole-firm AUM is over $2,500M, drop the person even if one fund is small. Backups: adv.news, rialytix.com, SEC IAPD (`adviserinfo.sec.gov`), or the firm's own "$X billion under management" claim.
- Record every check in the firm AUM cache (see `find-people.md`).

## Email patterns

Common formats at small investment firms, in rough order: `first@`, `flast@`, `first.last@`, `firstl@`, `firstlast@`. A single confirmed address at the firm settles the pattern.

Places to find a confirmed address:
- PitchBook
- The firm site's page source (see above)
- Press releases ("Media contact: …")
- Form ADV Part 2 brochure (the compliance officer's email)
- Conference speaker pages
- The tracker sheet's past emails (e.g. `apark@velocitycm.com` means Velocity uses `flast@`)

Public email-format pages (LeadIQ, RocketReach, ContactOut, Prospeo) often state a firm's format. They're weaker evidence: label the result `Guessed (format per <site>)`.

Don't send test emails or use email-verification services that need an account.

## Outlook Sent Items (optional do-not-contact check)

The message list is virtualized, so scrolling one row at a time is slow. Instead, run a `javascript_tool` loop that scrolls the list container and collects each row's `aria-label` (it contains the recipient and subject). Chrome's output filter blocks strings that look like query strings, so strip `?`, `&` and `=` from the text before returning it.

## Notes from the 2026-11-02 run (PitchBook signed out)

- **Mergr via WebSearch** (`allowed_domains: ["mergr.com"]`, queries like `Vanderbilt University principal private equity <city>`) surfaced more qualifying alumni than LinkedIn snippets did; Mergr bios usually state the degree. WebFetch on mergr.com returns 403, so confirm role on the firm site.
- **curl from Bash** is a cheap way to scan static firm pages for `mailto:` addresses and "Vanderbilt" (e.g. found curt.crofford@penningtoncreek.com). JS-rendered sites (Squarespace/Wix/Next) return nothing this way.
- Several strong-looking candidates (Tom Driscoll, Jack Lewin, Max Blank) were already on the tracker: run `dnc.py check` early, before researching emails.
- Firms that publish full team emails: Benford Capital (first@), Council Capital (flast@), CIVC (flast@).

## Notes from the 2026-11-05 run (PitchBook signed out, class-of-2020 rule added mid-run)

- Public sources rarely state a class year, so without PitchBook expect only a few people who pass the 2020-2026 rule. This run found 1.
- A Python crawl of firm team pages (homepage, then links with team/people/bio, grepping "Vanderbilt") covered about 240 firms in minutes and found bios and published emails that WebSearch missed. It finds mostly senior people, though, and few bios give years.
- `build_doc.py` and `dnc.py` treat every weekly doc in the folder as contacted, so a superseded doc blocks its names until it is removed.
- New Harbor no longer lists Jocelyn Stanley, and Council no longer lists John Davis, so Mergr bios can be stale.

## Notes from the second 2026-11-05 run (PitchBook monthly search limit)

- PitchBook was signed in, then showed "you have run the max amount of searches for this month" on the People Screener after three scripted passes through the 159-row Analyst + Associate search. Each page turn seems to count, so page through a search once, keep the rows, and don't reload or page back. The limit resets at the start of the next calendar month.
- If that message appears, stop using the screener and move to public sources. Don't try to get around the limit.
- The screener table has no name links, so profile URLs can't be scraped from it.
- All NY/NJ/CT people in that 159-row search are at firms over $2.5B or already on the do-not-contact list. The rest of the list is exhausted too, apart from the pool's check rows, which only need a class year.
