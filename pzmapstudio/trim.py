"""Trim a compiled map to a rectangular block of 256-tile cells."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

LOT = re.compile(r"^(world_|chunkdata_)?(-?\d+)_(-?\d+)(\.(?:lotheader|lotpack|bin))$")


def trim_map(source: str | Path, out: str | Path,
             x0: int, y0: int, x1: int, y1: int) -> Path:
    source = Path(source)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    kept = 0
    for path in source.iterdir():
        if not path.is_file():
            continue
        match = LOT.match(path.name)
        if not match:
            shutil.copy2(path, out / path.name)
            continue
        x, y = int(match.group(2)), int(match.group(3))
        if x0 <= x <= x1 and y0 <= y <= y1:
            shutil.copy2(path, out / path.name)
            if path.name.endswith(".lotheader"):
                kept += 1
    spawn = out / "spawnpoints.lua"
    if spawn.exists():
        def repl(match: re.Match) -> str:
            x, y = int(match.group(1)), int(match.group(2))
            if x0 * 256 <= x < (x1 + 1) * 256 and y0 * 256 <= y < (y1 + 1) * 256:
                return match.group(0)
            return ""
        text = spawn.read_text(errors="ignore")
        text = re.sub(r"\{\s*posX\s*=\s*(-?\d+),\s*posY\s*=\s*(-?\d+),\s*posZ\s*=\s*(-?\d+)\s*\},",
                      lambda m: (m.group(0) if x0 * 256 <= int(m.group(1)) < (x1 + 1) * 256
                                 and y0 * 256 <= int(m.group(2)) < (y1 + 1) * 256 else ""),
                      text)
        spawn.write_text(text)
    (out / "trim.info").write_text(
        f"source={source}\ncells={x0},{y0}..{x1},{y1}\nkept={kept}\n",
        encoding="utf-8",
    )
    return out
