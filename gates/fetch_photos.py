#!/usr/bin/env python3
"""Fetch openly licensed anchor photos (Wikimedia Commons) into gates/photos/ and write LICENSES.md.

    gates/.venv/bin/python gates/fetch_photos.py            # picks the first N acceptable files per species

Accepted licences: CC0, public domain, CC BY, CC BY-SA. Images are stored as 1280 px-wide JPEG thumbnails
under neutral names (p1.jpg ...) so a filename never leaks the species to a vision model.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "photos"
API = "https://commons.wikimedia.org/w/api.php"
SPECIES = [("Sepia officinalis", 3), ("Metasepia pfefferi", 3)]
OK_LICENSE = re.compile(r"^(cc0|pd|public domain|cc[- ]by(-sa)?[- ][\d.]+)", re.I)
UA = {"User-Agent": "cuttlefish-theme-gates/1.0 (https://github.com/wisechef-ai/cuttlefish-theme)"}


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def query(**params) -> dict:
    return json.loads(get(API + "?" + urllib.parse.urlencode({"format": "json", "formatversion": 2, **params})))


def candidates(species: str) -> list[dict]:
    q = query(action="query", generator="search", gsrsearch=f'"{species}" filetype:bitmap', gsrnamespace=6, gsrlimit=30,
              prop="imageinfo", iiprop="url|extmetadata|size", iiurlwidth=1280)
    out = []
    for page in q.get("query", {}).get("pages", []):
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if not OK_LICENSE.match(lic) or info.get("width", 0) < 800 or not info.get("thumburl"):
            continue
        if species.split()[1] not in page["title"] and species.split()[1] not in meta.get("ImageDescription", {}).get("value", ""):
            continue
        out.append({"title": page["title"], "thumb": info["thumburl"], "page": info["descriptionurl"], "license": lic,
                    "author": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "unknown"))).strip()[:70],
                    "licenseurl": meta.get("LicenseUrl", {}).get("value", "")})
    return out


def main() -> int:
    OUT.mkdir(exist_ok=True)
    rows, n = [], 0
    for species, count in SPECIES:
        for c in candidates(species)[:count]:
            n += 1
            name = f"p{n}.jpg"
            (OUT / name).write_bytes(get(c["thumb"]))
            rows.append((name, species, c))
    lines = ["# Anchor photo licences", "", "Real animals, openly licensed, fetched from Wikimedia Commons by `gates/fetch_photos.py`. "
             "Stored under neutral names so a filename never reveals the species to a vision model.", "",
             "| file | species | title | author | licence | source |", "|---|---|---|---|---|---|"]
    lines += [f'| {nm} | {sp} | {c["title"]} | {c["author"]} | [{c["license"]}]({c["licenseurl"]}) | {c["page"]} |' for nm, sp, c in rows]
    (OUT / "LICENSES.md").write_text("\n".join(lines) + "\n")
    print(f"{len(rows)} photos written to {OUT}")
    return 0 if len(rows) == sum(c for _, c in SPECIES) else 1


if __name__ == "__main__":
    sys.exit(main())
