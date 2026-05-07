# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.40"]
# ///
"""Scrape Google Maps primary photos for each place in london.md.

One-time setup (downloads Chromium ~150 MB):
    uv run --with playwright playwright install chromium

Run:
    uv run scripts/scrape_images.py

Idempotent: places already in images.json that have a downloaded file are skipped.
Re-fetch a single place:
    uv run scripts/scrape_images.py --force "Brick Lane Bookshop"
"""
import asyncio, json, os, re, sys, time, unicodedata, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_PATH = ROOT / "london.md"
IMAGES_DIR = ROOT / "images"
OUT_PATH = ROOT / "images.json"

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TARGET_SIZE = 480  # request this size from Google's CDN


def parse_md(text: str) -> list[dict]:
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


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def adjust_size(url: str, w: int = TARGET_SIZE, h: int = TARGET_SIZE) -> str:
    """Replace the Google photo size suffix (e.g. =w408-h408-k-no)."""
    return re.sub(r"=w\d+-h\d+-k-no(?:-[a-z0-9]+)?$", f"=w{w}-h{h}-k-no", url)


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as r:
        dest.write_bytes(r.read())


async def fetch_image_url(page, query_url: str) -> str | None:
    """Navigate to the search URL and return the primary place photo URL."""
    try:
        await page.goto(query_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return None

    # Dismiss the consent banner once per browser context (safe to call repeatedly)
    try:
        await page.click('button[aria-label*="Accept all"], button:has-text("Accept all")',
                         timeout=2500)
    except Exception:
        pass

    # If we land on a search results list, click the top result to load the place detail.
    try:
        first = await page.wait_for_selector(
            'a.hfpxzc, a[aria-label][href*="/maps/place/"]',
            timeout=4000
        )
        if first:
            try:
                await first.click(timeout=3000)
                await page.wait_for_timeout(1500)
            except Exception:
                pass
    except Exception:
        pass  # already on a place detail page (no list to click)

    # Wait for the place panel photo to materialise.
    try:
        await page.wait_for_selector(
            'img[src*="lh3.googleusercontent.com/gps-cs-s"], '
            'img[src*="lh5.googleusercontent.com/p/"], '
            'img[src*="lh3.googleusercontent.com/p/"]',
            timeout=10000,
        )
    except Exception:
        return None

    img_src = await page.evaluate(
        """() => {
            const re = /lh\\d\\.googleusercontent\\.com\\/(?:gps-cs-s|p)\\//;
            const imgs = [...document.querySelectorAll('img')]
                .filter(i => re.test(i.src || ''));
            // Prefer the largest naturally-rendered photo (the hero in the place panel).
            imgs.sort((a, b) =>
                (b.naturalWidth * b.naturalHeight) - (a.naturalWidth * a.naturalHeight)
            );
            return imgs[0]?.src || null;
        }"""
    )
    return img_src


async def main():
    sections = parse_md(MD_PATH.read_text())
    IMAGES_DIR.mkdir(exist_ok=True)

    images: dict = {}
    if OUT_PATH.exists():
        images = json.loads(OUT_PATH.read_text())

    forced: set[str] = set()
    args = sys.argv[1:]
    while args:
        a = args.pop(0)
        if a == "--force" and args:
            forced.add(args.pop(0))

    from playwright.async_api import async_playwright

    new_count = 0
    total = sum(len(s["entries"]) for s in sections)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=USER_AGENT, locale="en-GB",
                                        viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()

        done = 0
        for sec in sections:
            for entry in sec["entries"]:
                done += 1
                name = entry["name"]
                slug = slugify(name)
                jpg_path = IMAGES_DIR / f"{slug}.jpg"

                # Skip if we already have everything: a downloaded file AND a recorded remote URL.
                already_have_remote = name in images and images[name].get("remote")
                if jpg_path.exists() and already_have_remote and name not in forced:
                    continue
                # Backfill the manifest entry for previously-downloaded files (no JPG redownload).
                backfill_only = jpg_path.exists() and not already_have_remote and name not in forced
                if not entry["url"]:
                    print(f"  [{done}/{total}] {name}: no URL")
                    continue

                print(f"  [{done}/{total}] {name}", end=" ", flush=True)
                try:
                    img_url = await fetch_image_url(page, entry["url"])
                    if not img_url:
                        print("→ no image found")
                        # Record as missing so we don't keep retrying without --force
                        images[name] = {"slug": slug, "src": None}
                        continue
                    if backfill_only:
                        # Keep the existing JPG; just store the remote URL for high-res lightbox use.
                        images[name] = {
                            "slug": slug,
                            "src": str(jpg_path.relative_to(ROOT)).replace("\\", "/"),
                            "remote": img_url,
                        }
                        print("→ backfilled remote URL")
                        OUT_PATH.write_text(json.dumps(images, indent=2, ensure_ascii=False))
                        await asyncio.sleep(0.4)
                        continue
                    sized = adjust_size(img_url)
                    download(sized, jpg_path)
                    images[name] = {
                        "slug": slug,
                        "src": str(jpg_path.relative_to(ROOT)).replace("\\", "/"),
                        "remote": img_url,
                    }
                    new_count += 1
                    size_kb = jpg_path.stat().st_size // 1024
                    print(f"→ saved {jpg_path.name} ({size_kb} KB)")
                    # Persist manifest after every download so a crash doesn't lose progress
                    OUT_PATH.write_text(json.dumps(images, indent=2, ensure_ascii=False))
                except Exception as e:
                    print(f"ERROR: {e}")
                # be polite
                await asyncio.sleep(0.4)

        await browser.close()

    OUT_PATH.write_text(json.dumps(images, indent=2, ensure_ascii=False))
    found = sum(1 for v in images.values() if v.get("src"))
    print(f"\n→ {found}/{len(images)} have images ({new_count} new) — manifest at {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
