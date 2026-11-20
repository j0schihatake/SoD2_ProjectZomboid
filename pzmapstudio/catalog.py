"""Catalog of PZ assets, items and randomized-story clutter.

The catalog is intentionally built from the installed game files, so the agent
sees exactly what the current game build exposes instead of a hard-coded list.

Sources:
  media/tile_definitions/*.tiles.txt   tile names
  media/scripts/**/*.txt               item names
  media/lua/server/RandomizedWorldContent/StoryClutter/*.lua
                                       story clutter item tables
"""
from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class Catalog:
    tiles: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    stories: dict[str, list[str]] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tiles": sorted(set(self.tiles)),
            "items": sorted(set(self.items)),
            "stories": {k: sorted(set(v)) for k, v in sorted(self.stories.items())},
            "sources": self.sources,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Catalog":
        return cls(
            tiles=list(data.get("tiles", [])),
            items=list(data.get("items", [])),
            stories={k: list(v) for k, v in data.get("stories", {}).items()},
            sources=dict(data.get("sources", {})),
        )

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True).encode()
        path.write_bytes(gzip.compress(raw, 9))
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Catalog":
        return cls.from_dict(json.loads(gzip.decompress(Path(path).read_bytes())))

    def search(self, kind: str = "all", query: str = "", limit: int = 100) -> dict:
        query = query.lower()
        if kind in ("all", "tiles"):
            tiles = [t for t in sorted(set(self.tiles)) if query in t.lower()][:limit]
        else:
            tiles = []
        if kind in ("all", "items"):
            items = [i for i in sorted(set(self.items)) if query in i.lower()][:limit]
        else:
            items = []
        if kind in ("all", "stories"):
            stories = {
                name: items for name, items in sorted(self.stories.items())
                if query in name.lower() or any(query in item.lower() for item in items)
            }
            stories = dict(list(stories.items())[:limit])
        else:
            stories = {}
        return {"tiles": tiles, "items": items, "stories": stories}


def _read_tiles(media: Path, catalog: Catalog) -> None:
    folder = media / "tile_definitions"
    if not folder.is_dir():
        return
    found = 0
    for path in sorted(folder.glob("*.tiles.txt")):
        for line in path.read_text(errors="ignore").splitlines():
            match = re.match(r"\s*file\s*=\s*(\S+)", line)
            if match:
                continue
            match = re.match(r"\s*//\s*([A-Za-z0-9_]+_\d+)\s*$", line)
            if match:
                catalog.tiles.append(match.group(1))
                found += 1
    catalog.sources["tiles"] = f"{found} names from {folder}"


def _read_items(media: Path, catalog: Catalog) -> None:
    found = 0
    for path in sorted((media / "scripts").rglob("*.txt")):
        for line in path.read_text(errors="ignore").splitlines():
            match = re.match(r"\s*item\s+([A-Za-z0-9_.]+)\s*$", line)
            if match:
                name = match.group(1)
                if "." not in name:
                    name = f"Base.{name}"
                catalog.items.append(name)
                found += 1
    catalog.sources["items"] = f"{found} names from {media / 'scripts'}"


def _read_stories(media: Path, catalog: Catalog) -> None:
    folder = media / "lua" / "server" / "RandomizedWorldContent" / "StoryClutter"
    total = 0
    for path in sorted(folder.glob("*Definitions.lua")):
        text = path.read_text(errors="ignore")
        for match in re.finditer(r"StoryClutter\.([A-Za-z0-9_]+)\s*=\s*\{(.*?)\n\}", text, re.S):
            name = match.group(1)
            body = match.group(2)
            items = re.findall(r'"([^"]+)"', body)
            catalog.stories[name] = items
            total += len(items)
    catalog.sources["stories"] = f"{total} clutter items in {len(catalog.stories)} tables"


def build_catalog(pz_root: str | Path) -> Catalog:
    """Build from the game's ``projectzomboid`` directory."""
    root = Path(pz_root)
    media = root / "media" if (root / "media").is_dir() else root
    catalog = Catalog()
    _read_tiles(media, catalog)
    _read_items(media, catalog)
    _read_stories(media, catalog)
    return catalog


def iter_kinds(catalog: Catalog) -> Iterable[tuple[str, int]]:
    yield "tiles", len(set(catalog.tiles))
    yield "items", len(set(catalog.items))
    yield "stories", len(catalog.stories)
