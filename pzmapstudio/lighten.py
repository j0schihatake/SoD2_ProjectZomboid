"""Create a save-budget-light copy of a compiled map."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .pzlot import rewrite_cell

LOT = re.compile(r"^(world_|chunkdata_)?(-?\d+)_(-?\d+)(\.(?:lotheader|lotpack|bin))$")


def lighten_map(source: str | Path, out: str | Path) -> Path:
    """Drop room/building metadata from every cell, keeping all tile records."""
    source = Path(source)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cells = []
    for header in source.glob("*.lotheader"):
        parts = header.stem.split("_")
        cells.append((int(parts[-2]), int(parts[-1])))
    for cx, cy in cells:
        rewrite_cell(source, out, cx, cy, {}, strip_rooms=True)
    for path in source.iterdir():
        if path.is_file() and not LOT.match(path.name):
            shutil.copy2(path, out / path.name)
    return out
