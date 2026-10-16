"""Fetch the documentation the ground-truth tests read, and record it in a manifest.

    python scripts/fetch_sources.py

The copies land in ``tests/sources/`` (git-ignored: third-party text is never committed
or shipped). ``tests/sources/MANIFEST.json`` is tracked and records, for each file, the
URL, the fetch date, size, SHA-256 and licence. Tests that read a copy skip when it is
missing. Pass ``--check`` to fail when a fetched file no longer matches the manifest.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "tests" / "sources"
# limits 5.8.0, the release whose moving-window strategy the oracle fixture was captured from.
LIMITS = (
    "https://raw.githubusercontent.com/alisaifee/limits/cc5eafcc45488d9995d738e4de498e6d74dc6e9c"
)
SOURCES = {
    "limits-5.8.0-strategies.rst": (f"{LIMITS}/doc/source/strategies.rst", "MIT"),
}


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "taplimit-sources"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return bytes(response.read())


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "MANIFEST.json"
    check = "--check" in sys.argv
    old = json.loads(manifest_path.read_text("utf-8")) if manifest_path.is_file() else {}
    manifest = {}
    for name, (url, licence) in SOURCES.items():
        data = _fetch(url)
        digest = hashlib.sha256(data).hexdigest()
        if check and old.get(name, {}).get("sha256") != digest:
            print(f"{name}: changed since the manifest was written")
            return 1
        (ROOT / name).write_bytes(data)
        manifest[name] = {
            "url": url,
            "fetched": datetime.date.today().isoformat(),
            "size": len(data),
            "sha256": digest,
            "licence": licence,
        }
        print(f"{name}: {len(data)} bytes")
    if not check:
        text = json.dumps(manifest, indent=1, sort_keys=True) + "\n"
        manifest_path.write_text(text, "utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
