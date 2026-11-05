// Paste into javascript_tool on the Outlook Sent Items tab. Replace __SINCE__ with YYYY-MM-DD.
// Read-only: it scrolls the message list and opens nothing, so no read/unread state changes.
//
// Why it looks like this:
// - The list is virtualized: only the ~7 visible rows exist at a time, and they render late.
//   Fixed-delay scrolling dropped rows with no error (83 of 143 at first, then 1 in 111).
//   So each step waits for the rows to settle and must overlap the previous step; if it
//   doesn't, it backs up. Contiguous overlap is what proves no row was skipped.
// - aria-setsize on a row gives the folder's true count. aria-posinset is mostly 0, so don't use it.
// - Recipient, subject and timestamp are separate spans. The span[title] holds the full date,
//   such as "Thu 11/5/2026 2:19 PM", while the visible text says only "2:19 PM".
// - Chrome's output filter blocks query-string-looking text, so ? & = are stripped.
// - Results over 100 array items, or one long string, get cut off. Page through window.__rows.
const CUTOFF = new Date('__SINCE__');
const wait = ms => new Promise(r => setTimeout(r, ms));
let sc = document.querySelector('[role=option]');
while (sc && !(sc.scrollHeight > sc.clientHeight + 50 && /auto|scroll/.test(getComputedStyle(sc).overflowY))) sc = sc.parentElement;
const clean = s => (s || '').replace(/[?&=|]/g, ' ').replace(/\s+/g, ' ').trim();
const seen = new Map();
let oldest = null, setSize = 0, backups = 0;

const readRow = r => {
  setSize = Math.max(setSize, +r.getAttribute('aria-setsize') || 0);
  const label = r.getAttribute('aria-label') || '';
  const ds = [...r.querySelectorAll('span[title]')].find(s => /\d{1,2}\/\d{1,2}\/\d{4}/.test(s.getAttribute('title') || ''));
  if (!ds) return { key: 'nodate:' + clean(label).slice(0, 120), line: null };   // e.g. a calendar item
  const leaves = [...r.querySelectorAll('span')].filter(s => s.children.length === 0 && s.innerText.trim());
  const i = leaves.indexOf(ds);
  const when = ds.getAttribute('title');
  const subject = i >= 1 ? clean(leaves[i - 1].innerText) : '';
  const to = i >= 2 ? clean(leaves[i - 2].innerText) : '';
  const preview = clean((leaves[i + 1] && leaves[i + 1].innerText) || '').slice(0, 70);
  const d = new Date(when.replace(/^\w{3} /, ''));
  if (!isNaN(d) && (!oldest || d < oldest)) oldest = d;
  return { key: to + '|' + subject + '|' + when, line: [when, to, subject, /External sender/.test(label) ? 1 : 0, /Meeting/.test(label.slice(0, 40)) ? 1 : 0, preview].join(' | ') };
};
const snapshot = () => [...document.querySelectorAll('[role=option]')].map(readRow);
const settled = async () => {           // same rows twice in a row means rendering has caught up
  let last = '', rows = [];
  for (let i = 0; i < 12; i++) {
    await wait(150);
    rows = snapshot();
    const sig = rows.map(r => r.key).join('\n');
    if (sig === last && rows.length) break;
    last = sig;
  }
  return rows;
};

sc.scrollTop = 0;
await wait(800);
let prev = new Set(), step = Math.max(120, sc.clientHeight * 0.3);
for (let i = 0; i < 1500; i++) {
  const rows = await settled();
  const overlaps = !prev.size || rows.some(r => prev.has(r.key));
  if (!overlaps) {                      // jumped past something: go back and take a smaller step
    backups++;
    sc.scrollTop -= step / 2;
    continue;
  }
  rows.forEach(r => { if (!seen.has(r.key)) seen.set(r.key, r.line); });
  prev = new Set(rows.map(r => r.key));
  if (oldest && oldest < CUTOFF) break;
  if (sc.scrollTop + sc.clientHeight >= sc.scrollHeight - 4) break;
  sc.scrollTop += step;
}
const reachedEnd = sc.scrollTop + sc.clientHeight >= sc.scrollHeight - 4;
sc.scrollTop = 0;
window.__rows = [...seen.values()].filter(Boolean);
({
  rows: window.__rows.length, seenIncludingCalendarItems: seen.size, folderTotal: setSize, backups,
  reachedCutoff: !!(oldest && oldest < CUTOFF), reachedEnd,
  // A complete read reaches the cutoff, or reaches the end with seenIncludingCalendarItems === folderTotal.
  complete: !!(oldest && oldest < CUTOFF) || (reachedEnd && seen.size === setSize),
  page1: window.__rows.slice(0, 90)
})
// Next pages: window.__rows.slice(90, 180), and so on.
