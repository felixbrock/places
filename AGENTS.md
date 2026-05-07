# Notes for AI agents working in this repo

The user maintains a personal London places guide here. There are four parallel data sources that must stay in sync:

1. `london.md` — entries (name, URL, description, tags, section)
2. `coords.json` — geocoded lat/lng per place (via `scripts/geocode_via_google.py`)
3. `images/<slug>.jpg` + `images.json` — primary photo per place (via `scripts/scrape_images.py`)
4. The user's Google Maps shared list `london_recommendations`, edited via Playwright

The user will only edit `london.md`. Everything else is the agent's job.

## Skills

Three skills under `.claude/skills/` codify the maintenance workflows. Pick the one matching the user's intent:

- **`add-place`** — user added a new entry to `london.md` (typically just a name)
- **`edit-place`** — user changed an existing entry (rename, URL, description, tags)
- **`delete-place`** — user removed an entry

Each skill describes the full process end-to-end. Run every step — partial completion leaves the four data sources out of sync and the page silently misbehaves.

## Reference

`docs/maps-list-automation.md` — the Playwright gotchas for editing the Google Maps shared list. Read it once before any add/edit/delete operation that touches the Maps list.
