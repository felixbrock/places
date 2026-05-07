#!/usr/bin/env python3
"""Geocode places from london.md via Nominatim (OpenStreetMap).
Writes/updates ../coords.json. Re-running is idempotent — only new
places (those not already in coords.json) are looked up.

Run: python3 scripts/geocode.py
"""
import json, time, re, urllib.parse, urllib.request, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD_PATH = os.path.join(ROOT, "london.md")
OUT_PATH = os.path.join(ROOT, "coords.json")
USER_AGENT = "london-places-guide/1.0 (https://github.com/felixbrock/places)"

# Manual overrides for places where Nominatim returns the wrong result
# or doesn't find anything. Coords sourced from Google Maps directly.
OVERRIDES = {
    "Brick Lane Vintage Market": (51.5217, -0.0721),       # Old Truman Brewery basement
    "Aether Coffee Lab": (51.5042, -0.0188),               # Wood Wharf, Canary Wharf
    "Special Guests Coffee": (51.5180, -0.1535),           # Aybrook St, Marylebone
    "St Clair Cafe": (51.5101, -0.2068),                   # Portland Rd, Holland Park
    "Nola Coffee": (51.4709, -0.0681),                     # 224 Rye Ln, Peckham
    "Cöödie": (51.4742, -0.0680),                          # 100 Peckham High St
    "Duck & Waffle": (51.5163, -0.0813),                   # Heron Tower, 110 Bishopsgate
    "Plaza Khao Gaeng": (51.5161, -0.1287),                # Arcade Centre Point
    "Heritage Dulwich": (51.4413, -0.0945),                # 101 Rosendale Rd, SE21
    "Blitz Memorial (Wapping)": (51.5037, -0.0599),        # Wapping High St
    "Mudchute Park and Farm": (51.4925, -0.0145),          # Pier St, Isle of Dogs
    "Greenwich Foot Tunnel North": (51.4881, -0.0098),     # Island Gardens
}


def parse_md(text):
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
                cur = {"name": line[2:].strip(), "url": "", "tags": []}
            elif re.match(r"^\s+- ", line) and cur:
                c = re.sub(r"^\s+- ", "", line).strip()
                if c.startswith("http"):
                    cur["url"] = c
                elif c.lower().startswith("tags:"):
                    cur["tags"] = [t.strip() for t in c[len("Tags:") :].split(",") if t.strip()]
        if cur:
            entries.append(cur)
        sections.append({"category": category, "entries": entries})
    return sections


def query_from_url(url):
    m = re.search(r"[?&]query=([^&]+)", url)
    if m:
        return urllib.parse.unquote_plus(m.group(1))
    return None


def geocode(query):
    qs = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
    req = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/search?{qs}",
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())
        if not data:
            return None
        return {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"])}


def main():
    with open(MD_PATH) as f:
        sections = parse_md(f.read())

    coords = {}
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH) as f:
            coords = json.load(f)

    # Apply overrides (always trust them)
    for name, (lat, lng) in OVERRIDES.items():
        coords[name] = {"lat": lat, "lng": lng, "source": "override"}

    total = sum(len(s["entries"]) for s in sections)
    done = 0
    new_count = 0

    for sec in sections:
        for e in sec["entries"]:
            done += 1
            name = e["name"]
            if name in coords:
                continue
            q = query_from_url(e["url"])
            if not q:
                print(f"  [{done}/{total}] {name!r:50} no query in URL", file=sys.stderr)
                continue
            print(f"  [{done}/{total}] geocoding {q!r:60}", end=" ... ", flush=True)
            try:
                result = geocode(q)
                if result:
                    coords[name] = {"lat": result["lat"], "lng": result["lng"], "source": "nominatim", "query": q}
                    print(f"OK  {result['lat']:.4f}, {result['lng']:.4f}")
                    new_count += 1
                else:
                    print("NOT FOUND")
            except Exception as ex:
                print(f"ERROR: {ex}")
            time.sleep(1.05)  # Nominatim policy: ≤1 req/sec

    with open(OUT_PATH, "w") as f:
        json.dump(coords, f, indent=2, ensure_ascii=False)
    print(f"\n→ Wrote {len(coords)} coords ({new_count} new) to {OUT_PATH}")


if __name__ == "__main__":
    main()
