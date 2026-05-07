---
name: edit-place
description: Use when the user changes an existing entry in london.md (rename, change URL, edit description or tags, move sections) and asks the agent to propagate the change. Different changes require different downstream updates — re-geocode, re-scrape image, update the Maps list note. Run only the steps the diff actually requires.
---

# Editing an existing place

Different fields cascade to different systems. Keep the edits minimal: don't re-geocode if only the description changed, don't re-fetch the photo if only a tag was added.

## 1. Identify what changed

Read the relevant entry in `london.md` and compare against:

- `coords.json` — has `source` and `query` (the URL it was geocoded from)
- `images.json` — has `slug`, `src`, `remote`
- The Google Maps shared list — manual check via Playwright if needed

Use `git diff london.md` if there's an unstaged change, or ask the user what they changed.

## 2. Cascade by field

### Name changed

Hardest case. Slug derives from the name, so the cached image filename is now stale.

1. Update `images.json`: rename the entry's key from old name to new name.
2. Compute the new slug (`scripts/scrape_images.py` `slugify` is the reference: NFD normalise, strip accents, lowercase, non-alphanum → hyphens). Rename `images/<old-slug>.jpg` to `images/<new-slug>.jpg` and update `src` accordingly.
3. Update `coords.json`: rename the entry's key from old to new name.
4. In the Maps list: delete the row with the old name, then add the new name following `add-place` step 8.
5. Don't blindly re-run the scripts — they'd re-fetch on top of the rename and create extras.

### URL changed (typically when the user gives a more specific shortlink)

The URL is what the geocoder and image scraper consume.

1. Force-refresh the geocode for that one entry:
   ```bash
   cd /home/felix/repos/places
   uv run scripts/geocode_via_google.py --force
   ```
   (`--force` re-fetches everything; if you only want the one entry, edit the script's `if existing.get("source") == "google"` check temporarily, or delete the entry from `coords.json` first so the un-forced run picks it up.)
2. Force-refresh the image:
   ```bash
   uv run scripts/scrape_images.py --force "Place Name"
   ```
3. In the Maps list: replace the row. Delete the existing one (use the row's `button[aria-label="Delete"]`), add the new one with the same note text.

### Description or tags changed

No coords / image impact. Only the page render and the Maps list note need updating.

1. The page reads `london.md` at runtime, so the change is immediate after reload.
2. In the Maps list: walk to the row, locate its `<textarea>` (3-parents-up technique — see `docs/maps-list-automation.md`), rewrite the note via `execCommand('insertText')`, body-click, wait ≥ 2.5 s, verify by reading back `ta.value`, full-reload to confirm persistence.

### Section changed

A place moved from e.g. Cafes to Restaurants.

1. Page rerenders correctly (section is derived from markdown).
2. Map pin colour changes (it keys off `data-cat`).
3. Maps list does **not** track sections — no list edit needed.

### Maps URL kept, only minor edits

If only the description / tags changed and the URL is identical, you're in the "Description or tags changed" branch above.

## 3. Always finish by reloading

- Refresh the local server (`http://localhost:8765` if running) and check the entry renders correctly under the right tab/section/area, with the right photo and pin.
- Hard-reload the Maps list page and confirm the place + note still match.

If anything looks off (e.g. the pin is now far from the rest of its area, or the photo no longer matches the description), inspect the failing field and re-run the relevant cascade.

## Maps list automation reference

For everything Playwright-related (URL, gotchas, find-by-name, virtualisation, removing rows), see `docs/maps-list-automation.md`. In particular: do not use `find(visible)` to locate a `<textarea>` — that always returns row 0 and silently corrupts whatever was in the first row.
