# Google Maps list automation

The user's `london_recommendations` saved list at https://maps.app.goo.gl/TanA1A3spUNxBKoNA is a second-canonical view of the guide. The page consumes its share-link, but more importantly the user opens the list directly in the Google Maps app on their phone when planning a day. Markdown / coords / images / Maps list must stay in sync.

There is no API for saved lists — every edit goes through Playwright (MCP `mcp__plugin_playwright_playwright__*`). The patterns below were learned the hard way; deviate at your peril.

## Setup

Open this URL in Playwright to land directly in edit mode:

```
https://www.google.com/maps/@51.4414442,-0.0585374,14z/data=!4m6!1m2!10m1!1e1!11m2!2sVxYuPOrMvxHk3VYYG-en1g!3e3?entry=ttu
```

Sign-in with the user's Google account is required (one-time per browser session). If the page does not show "Add a place" / per-row Delete buttons, the user is not signed in. Prompt them to sign in via the Playwright window — there is no headless workaround for saved lists.

Page title should read `london_recommendations - Google Maps` once loaded.

## Adding a place

1. Click `button[aria-label="Add a place"]`.
2. Drive the search input (`input[aria-label="Search for a place to add"]`) using a React-friendly setter:
   ```js
   const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
   setter.call(input, "Place Name + street/area + London");
   input.dispatchEvent(new Event("input", { bubbles: true }));
   ```
3. **Always include "London" or a street name** in the query. Bare names misfire — `Hampstead Village London` returns "Village Vet Hampstead" otherwise.
4. Poll for suggestions: `[role="grid"][aria-label="Suggestions"] [role="gridcell"]`. Read `cells[0].textContent` and **verify it matches the right place** before clicking. Google sometimes prefers a corporate-office listing over the architectural/specific one (this happened with Lloyd's vs Lloyd's of London, and Nandine vs Nandine Yek). If the first suggestion is wrong, refine the query (add street, postcode, distinguishing word) and retry.
5. Click the verified suggestion. Wait ~1.5–2 s for the place to commit to the list.
6. New places appear at the **top** of the list; DOM order is most-recently-added first.

## Per-place notes — the critical gotcha

`document.querySelectorAll('textarea[aria-label="Note"]')` returns **one textarea per row** but they all coexist in the DOM. **Do not** use `.find(visible)` or `[0]` — those always return row 0's textarea, so every write lands in the *first* row of the list and silently corrupts whatever was there.

The right way:

1. The newly-added place has an `Add note` button. Find it: `document.querySelector('button[aria-label="Add note"]')` (only un-noted rows expose this button, so right after adding a place there is exactly one).
2. **Walk up 3 parents** from that button to the row container.
3. `row.querySelector('textarea[aria-label="Note"]')` gives THAT row's textarea — only this one.
4. Click `Add note` to reveal the textarea (it is rendered but hidden until clicked).

### Filling the text

`.value = ...` via React-style setter does **not** persist server-side. Use `execCommand`:

```js
ta.focus();
ta.select();
document.execCommand("delete");
document.execCommand("insertText", false, text);
document.body.click();   // commits
// then wait at least 2500ms for the autosave debounce
```

If you skip the body click, no commit fires. If you skip the wait, the next operation can race the autosave and the change is lost.

### Verify

Read back `ta.value` and compare to the expected text. If it doesn't match, retry — don't blindly continue.

After all writes, **reload the page** (full navigation, not in-app) and confirm the notes persisted. Autosave can silently drop a write under load.

## Note format

Use the same format as existing notes in the list (the page parses these for the popup, so consistency matters):

```
What it is: <one short sentence description>. Tags: <comma-separated tags>
```

Example:

```
What it is: Speciality coffee shop and in-house roastery on Lower Marsh near Waterloo, with a deep pour-over menu. Tags: coffee, speciality, waterloo
```

This mirrors the markdown entry — same description, same tags. When in doubt, copy from `london.md` verbatim.

## Finding an existing place

The list panel is virtualised — only ~20 rows are in the DOM at once. To find an arbitrary place:

```js
const scrollers = [...document.querySelectorAll("div")]
  .filter(d => d.scrollHeight > d.clientHeight + 100);
scrollers.sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight));
const scroller = scrollers[0];
// scroll in 400–700 px steps, polling each iteration for your target
```

### Place-row name extraction

Place buttons have **empty `aria-label`**; the name is in `textContent`, formatted as `"NAME 4.6(1,234)Category "`. Strip with:

```js
text.match(/^(.+?)(\d\.\d\(|$)/)?.[1].trim()
```

Architectural / non-business places may not have a rating, in which case the regex's `$` branch takes the whole text.

### Abbreviated street names

Google abbreviates several street names — match against these forms when looking up the markdown name:

| In our markdown | In Google's row text |
|---|---|
| Wapping High Street | Wapping High St |
| Brick Lane | Brick Ln |
| Chiltern Street | Chiltern St |
| Redchurch Street | Redchurch St |
| Portobello Road | Portobello Rd |
| Golborne Road | Golborne Rd |
| New Bond Street | New Bond St |
| Old Bond Street | Old Bond St |

## Editing an existing note

Use the row-walking technique above to locate the right `<textarea>`, then the same `execCommand` write + body click + 2.5 s wait. If the row already has a note, the textarea exists already — no need to click `Add note`.

## Removing a place

In edit mode each row exposes a `button[aria-label="Delete"]`. Walk up from the place button to its row container, then `row.querySelector('button[aria-label="Delete"]')`. Click it; Google deletes immediately (no confirmation dialog under normal flow). Wait ~2 s and verify the row is gone.

If you are outside edit mode, navigate to the place's own page and toggle the "Saved" menu to uncheck `london_recommendations`. Slower but works.

## Verification

After any edit, full-reload the list URL and re-walk the rows to confirm the change persists. Autosave is reliable but not instant; a too-quick close-and-reopen can lose the last write.
