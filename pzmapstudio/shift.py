"""Shift a compiled map by whole 256-tile cells.

Renames .lotheader/.lotpack/chunkdata files, updates spawn points and simple
worldmap cell coordinates. Headers keep local room rectangles, so rooms and
buildings survive a move. Worldmap binary and complex object files are copied
unchanged; regenerate them if the map has them.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

CELL = 256
LOT = re.compile(r"^(world_|chunkdata_)?(\d+)_(\d+)(\.(?:lotheader|lotpack|bin))$")


def shift_spawnpoints(text: str, dx: int, dy: int) -> str:
    def repl(match: re.Match) -> str:
        x, y = int(match.group(1)) + dx * CELL, int(match.group(2)) + dy * CELL
        return f"posX = {x}, posY = {y}"
    return re.sub(r"posX\s*=\s*(-?\d+),\s*posY\s*=\s*(-?\d+)", repl, text)


def shift_worldmap(text: str, dx: int, dy: int) -> str:
    def repl(match: re.Match) -> str:
        return f'<cell x="{int(match.group(1)) + dx}" y="{int(match.group(2)) + dy}"'
    return re.sub(r'<cell x="(-?\d+)" y="(-?\d+)"', repl, text)


def shift_map(source: str | Path, out: str | Path, dx: int, dy: int,
              shift_objects: bool = False) -> Path:
    source = Path(source)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if not path.is_file():
            continue
        match = LOT.match(path.name)
        if not match:
            shutil.copy2(path, out / path.name)
            continue
        prefix, x, y, suffix = match.group(1) or "", int(match.group(2)), int(match.group(3)), match.group(4)
        target = out / f"{prefix}{x + dx}_{y + dy}{suffix}"
        shutil.copy2(path, target)
    spawn = out / "spawnpoints.lua"
    if spawn.exists():
        spawn.write_text(shift_spawnpoints(spawn.read_text(errors="ignore"), dx, dy))
    worldmap = out / "worldmap.xml"
    if worldmap.exists():
        worldmap.write_text(shift_worldmap(worldmap.read_text(errors="ignore"), dx, dy))
    if shift_objects:
        for name in ("objects.lua", "worldmap-annotations.lua"):
            path = out / name
            if not path.exists():
                continue
            text = path.read_text(errors="ignore")
            # Conservative: shift explicit x=/y= and posX=/posY= pairs.
            text = re.sub(r"(?i)(\bx\s*=\s*)(-?\d+)(\s*,\s*y\s*=\s*)(-?\d+)",
                          lambda m: f"{m.group(1)}{int(m.group(2)) + dx * CELL}{m.group(3)}{int(m.group(4)) + dy * CELL}",
                          text)
            path.write_text(text)
    return out
