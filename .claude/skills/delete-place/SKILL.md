---
name: delete-place
description: Use when the user removes an entry from london.md (or asks the agent to delete a place). Removes the entry from all four data sources — markdown, coords.json, images, and the Google Maps shared list — keeping them in sync.
---

# Deleting a place from the guide

Four data sources to clean up. Skip any and the page will either show stale data or break.

## 1. Confirm what's being deleted

If the user removed the entry from `london.md` themselves, read the surrounding context and figure out the exact name (it's the key into all the other systems).

If the user asked you to delete it, remove the markdown block first — the entry block is:

```
- Place Name
  - https://...
  - What it is: ...
  - Tags: ...
```

Delete all 4 lines. Don't leave dangling sub-bullets.

## 2. Remove from coords.json

Read the file, delete the key matching the place name, write it back. Preserve indentation/formatting (`indent=2`).

```bash
python3 -c "
import json
p = '/home/felix/repos/places/coords.json'
d = json.load(open(p))
d.pop('Place Name', None)
json.dump(d, open(p, 'w'), indent=2, ensure_ascii=False)
"
```

## 3. Remove the image and manifest entry

```bash
# Compute the slug the same way scrape_images.py does
slug=$(python3 -c "import unicodedata, re, sys; s = sys.argv[1]; s = unicodedata.normalize('NFD', s.lower()); s = ''.join(c for c in s if not unicodedata.combining(c)); print(re.sub(r'[^a-z0-9]+', '-', s).strip('-'))" "Place Name")

rm -f /home/felix/repos/places/images/${slug}.jpg

# Remove from manifest
python3 -c "
import json
p = '/home/felix/repos/places/images.json'
d = json.load(open(p))
d.pop('Place Name', None)
json.dump(d, open(p, 'w'), indent=2, ensure_ascii=False)
"
```

## 4. Remove from the Google Maps shared list

Use Playwright (MCP `mcp__plugin_playwright_playwright__*`). Follow `docs/maps-list-automation.md` for setup.

1. Open the list edit URL, wait for sign-in if needed.
2. Find the row by walking the virtualised list — see "Finding an existing place" in `docs/maps-list-automation.md`. Remember: place names with `Street` may be abbreviated to `St` or `Rd` in Google's row text.
3. Walk up from the place button to the row container, find `button[aria-label="Delete"]` inside that row. Click it.
4. Wait ~2 s. The row vanishes — no confirmation dialog under normal flow.
5. Verify: re-walk the rows and confirm the row is gone. Hard-reload to be sure.

If the place is currently filtered out of the visible map area on Google's side, sometimes the list virtualisation doesn't render its row. Scroll the list panel to bring it into view first.

## 5. Verify

- `grep "Place Name" london.md` — no matches.
- `python3 -c "import json; print('Place Name' in json.load(open('/home/felix/repos/places/coords.json')))"` — `False`.
- `python3 -c "import json; print('Place Name' in json.load(open('/home/felix/repos/places/images.json')))"` — `False`.
- `ls /home/felix/repos/places/images/<slug>.jpg` — no such file.
- Maps list reload — place not present.
- Local page (`python3 -m http.server 8765`) — entry not in the list, no orphan pin on the map.

If any check fails, fix before reporting done.
