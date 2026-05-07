---
name: add-place
description: Use when the user adds a new place to london.md (typically just `- Some Place Name` with no details, sometimes with a Google Maps shortlink) and asks the agent to fill in the rest. Researches the place, completes the markdown entry, runs geocode + image scrapers, and adds the place to the user's Google Maps shared list. Run end-to-end — partial completion leaves the four data sources (markdown, coords.json, images, Maps list) out of sync.
---

# Adding a place to the guide

The user maintains four parallel data sources. When they add a new place, all four must be updated:

1. `london.md` — the source of truth for entries (name, URL, description, tags, section)
2. `coords.json` — geocoded lat/lng per place, used by the map
3. `images/<slug>.jpg` + `images.json` — primary photo per place
4. The Google Maps shared list `london_recommendations` — alternate "by area" view

The user will only ever do step 1, sometimes incompletely. Your job is to bring the others in line.

## 1. Find the pending entry/entries

Read `london.md`. Pending entries usually look like:

```
- Calico Coffee
```

or

```
- The Jackalope
  - https://maps.app.goo.gl/XY3T86WAbHuXCCzZA
  - tbd
```

`grep -n "tbd\|TBD" london.md` plus a check for entries with no sub-bullets is a good way to find them. There may be more than one.

If the user said which section to put it in, respect that. Otherwise infer from the place type.

## 2. Research the place

Use `WebSearch` and `WebFetch` to confirm:

- **Official name** — match the place's own spelling (e.g. "Lloyd's Building" with apostrophe, "Naïfs" with diaeresis).
- **Kind of place** — cafe, restaurant, shop, etc. Drives the section.
- **Address / street / neighborhood** — needed for both the description and a precise Maps URL.
- **One distinctive feature** — what makes it worth visiting? That feature goes in the description.

If the user provided a `maps.app.goo.gl/...` shortlink, follow it (`WebFetch` will redirect once). The redirect target is `/maps/place/<name>/@<lat>,<lng>,...` — confirms the place identity and gives you the canonical URL.

## 3. Construct the Maps URL

Two options, in order of preference:

**Preferred** — if the user gave you a shortlink, use it directly:

```
- Some Place
  - https://maps.app.goo.gl/abc123
```

This points to a specific Google Maps listing and is unambiguous.

**Fallback** — a search URL with name + street + London:

```
- Some Place
  - https://www.google.com/maps/search/?api=1&query=Place+Name+Street+Area+London
```

Always include "London" or a street name in the query — bare names misfire. (The geocoder follows this URL and Google may pick the wrong place if the query is too generic.)

## 4. Pick the right section

```
## Shops · ## Cafes · ## Restaurants · ## Street Food
## Nature · ## Buildings/Architecture · ## Markets · ## Streets
```

Skim neighbors in the chosen section to feel the style. Place the new entry in a sensible position (often at the end of the section, but match user intent if obvious).

## 5. Write the entry

Schema:

```
- [Place Name]
  - [Maps Link]
  - What it is: [One short sentence description]
  - Tags: [comma-separated tags]
```

Indent sub-bullets with **two spaces**. (Some existing entries use 4 — both parse fine, but 2 is the dominant style.)

### Description style

One short sentence with one distinctive detail. Match these examples:

- "Counter-seat Thai restaurant on Brewer Street, Soho, cooking over open fire and clay pots."
- "24-hour British restaurant on the 40th floor of Heron Tower, famous for its namesake duck-and-waffle dish and the view."
- "Friendly speciality coffee shop on Rye Lane in Peckham, run by a musician couple, with a minimal wood-panelled interior."

Format: `[adjective] [type] on [street]/[in [area]], [distinctive detail]`. Avoid "if you want…" or second-person — describe the place, don't address the reader.

### Tags

Use the established corpus first:

```bash
grep -h "Tags:" london.md | tr ',' '\n' | sed 's/.*Tags: //' | sort -u
```

Always include:

- A **primary type tag** — `food`, `shopping`, `coffee`, `market`, `nature`, `architecture`, `street`, `street-food`.
- An **area tag** if the place is in a recognised neighborhood. AREA_TAGS in `index.html` is the canonical list (`peckham`, `marylebone`, `soho`, etc.). The page colours these specially, so picking one already in the list keeps the filter UI tidy.
- **Descriptive feature tags** when relevant — `vegan`, `view`, `free`, `late-night`, `brunch`, `vintage`, `speciality`, `riverside`, etc.

Avoid creating new tags when an existing one fits. New tags are fine when nothing existing matches.

## 6. Geocode

```bash
cd /home/felix/repos/places
uv run scripts/geocode_via_google.py
```

Idempotent — skips entries with `source: "google"` already. Visits the Maps URL, follows the redirect, reads the canonical `!3d{lat}!4d{lng}` from the place page URL. Output should show `→ <lat>, <lng>` for the new entry; if it shows `no coords found`, the URL is wrong (refine and retry with `--force "Place Name"`).

## 7. Scrape image

```bash
cd /home/felix/repos/places
uv run scripts/scrape_images.py
```

Idempotent — only fetches the primary photo for entries that don't have a JPG. Saves to `images/<slug>.jpg` (slug = lowercased, accent-stripped, hyphen-separated name). Updates `images.json` with both the local path and the remote Google CDN URL (used by the lightbox high-res view).

If the script writes `→ no image found`, Google didn't return a primary photo — usually means the place page didn't load fully (try `--force "Name"`) or the URL points to the wrong listing.

## 8. Add to the Google Maps shared list

Follow `docs/maps-list-automation.md` end-to-end. Concretely:

1. Open the list edit URL in Playwright.
2. Click `Add a place`, type the query (include a street or "London"), verify the suggestion is the right place, click cell 0.
3. Walk up 3 parents from the new row's `Add note` button to find the row's textarea (do **not** use `find(visible)` — that always returns row 0).
4. Write the note in this format using `execCommand('insertText')`:
   ```
   What it is: <description>. Tags: <tag1, tag2, ...>
   ```
   (Same description as the markdown, comma-joined tags.)
5. Click `document.body` to commit, **wait ≥ 2.5 s**, then read back `ta.value` and verify.
6. **Full-reload** the page and re-walk the rows to confirm the place + note both persisted.

If Google's first suggestion is the wrong listing (a corporate office or sister shop), refine the query and re-add. This happened with Lloyd's Building (vs. Lloyd's of London) and Nandine on Camberwell Church Street (vs. Nandine Yek on Vestry Road).

## 9. Verify everything

End by checking:

- `coords.json` has the new entry with `source: "google"` and plausible coords (within ~0.05° of central London).
- `images/<slug>.jpg` exists and is non-empty.
- `images.json` has the entry with `slug`, `src`, and `remote` populated.
- The Google Maps list (after a hard reload) shows the place plus the note.
- Open the local server (`cd places && python3 -m http.server 8765`) and load the page; the new entry should appear under the right Type tab, with its photo and a pin in the right spot on the map.

If any check fails, fix before reporting done.
