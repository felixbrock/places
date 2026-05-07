# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.40"]
# ///
"""Geocode every place by visiting its Google Maps page and reading the
coordinates straight from the resulting place URL — much more accurate than
Nominatim, which had been mis-locating several Canary Wharf entries by 250m+.

Pre-req (one-time):
    uv run --with playwright playwright install chromium

Run:
    uv run scripts/geocode_via_google.py

Idempotent: by default skips entries already in coords.json that have
`source: "google"`. Pass `--force` to refetch all.
"""
import asyncio, json, os, re, sys, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "london.md"
OUT_PATH = ROOT / "coords.json"
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def parse_md(text: str):
    before_notes = re.split(r"^#\s+\\?_Notes", text, flags=re.M)[0]
    parts = re.split(r"^##\s+", before_notes, flags=re.M)[1:]
    sections = []
    for part in parts:
        lines = part.split("\n")
        category = lines[0].strip()
        if category.startswith("_") or category.startswith("\\_"):
            continue
        entries, cur = [], None
        for line in lines[1:]:
            if re.match(r"^- ", line):
                if cur:
                    entries.append(cur)
                cur = {"name": line[2:].strip(), "url": ""}
            elif re.match(r"^\s+- ", line) and cur:
                c = re.sub(r"^\s+- ", "", line).strip()
                if c.startswith("http"):
                    cur["url"] = c
        if cur:
            entries.append(cur)
        sections.append({"category": category, "entries": entries})
    return sections


async def fetch_coords(page, query_url: str):
    """Navigate to the search URL, wait for the redirect to a place page,
    and extract the canonical coords from the !3d{lat}!4d{lng} pattern."""
    try:
        await page.goto(query_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return None

    # Dismiss consent banner if it appears (Google EU consent flow)
    try:
        await page.click(
            'button[aria-label*="Accept all"], button:has-text("Accept all")',
            timeout=2500,
        )
    except Exception:
        pass

    # Wait for the URL to change to a place page
    for _ in range(20):
        url = page.url
        if "/maps/place/" in url and re.search(r"!3d-?\d+\.\d+!4d-?\d+\.\d+", url):
            break
        await asyncio.sleep(0.5)

    url = page.url
    m = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", url)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Fallback: @lat,lng in URL (less canonical — uses map view centre)
    m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


async def main():
    sections = parse_md(MD_PATH.read_text())
    coords: dict = {}
    if OUT_PATH.exists():
        coords = json.loads(OUT_PATH.read_text())

    force = "--force" in sys.argv

    from playwright.async_api import async_playwright

    total = sum(len(s["entries"]) for s in sections)
    done = 0
    updated = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=USER_AGENT, locale="en-GB",
            viewport={"width": 1280, "height": 900},
        )
        page = await ctx.new_page()

        for sec in sections:
            for entry in sec["entries"]:
                done += 1
                name = entry["name"]
                if not entry["url"]:
                    print(f"  [{done}/{total}] {name}: no URL")
                    continue

                existing = coords.get(name) or {}
                if not force and existing.get("source") == "google":
                    continue

                print(f"  [{done}/{total}] {name}", end=" ", flush=True)
                try:
                    result = await fetch_coords(page, entry["url"])
                    if not result:
                        print("→ no coords found")
                        continue
                    lat, lng = result
                    old = (existing.get("lat"), existing.get("lng"))
                    coords[name] = {
                        "lat": lat,
                        "lng": lng,
                        "source": "google",
                        "query": entry["url"],
                    }
                    updated += 1
                    drift_msg = ""
                    if old[0] is not None:
                        # crude drift in meters
                        dlat = (lat - old[0]) * 111000
                        dlng = (lng - old[1]) * 111000 * 0.6  # London latitude
                        d = (dlat * dlat + dlng * dlng) ** 0.5
                        if d > 30:
                            drift_msg = f"  ⚠ drift {int(d)}m"
                    print(f"→ {lat:.6f}, {lng:.6f}{drift_msg}")
                    # Persist after each entry
                    OUT_PATH.write_text(json.dumps(coords, indent=2, ensure_ascii=False))
                except Exception as e:
                    print(f"ERROR: {e}")
                await asyncio.sleep(0.3)

        await browser.close()

    OUT_PATH.write_text(json.dumps(coords, indent=2, ensure_ascii=False))
    print(f"\n→ {updated} updated, {len(coords)} total in {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
