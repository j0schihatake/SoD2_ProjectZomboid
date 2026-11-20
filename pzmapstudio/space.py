"""Check free world-cell space for a new map."""
from __future__ import annotations

from pathlib import Path

# Compiled extents of the vanilla Knox Country map; never place a new map here.
VANILLA_BOX = (0, 0, 77, 62)


def map_extents(map_dir: str | Path) -> tuple[int, int, int, int] | None:
    keys = []
    for header in Path(map_dir).glob("*.lotheader"):
        parts = header.stem.split("_")
        try:
            keys.append((int(parts[-2]), int(parts[-1])))
        except (ValueError, IndexError):
            continue
    if not keys:
        return None
    return (min(x for x, _ in keys), min(y for _, y in keys),
            max(x for x, _ in keys), max(y for _, y in keys))


def extents(paths: list[str | Path]) -> list[tuple[int, int, int, int]]:
    result = []
    for path in paths:
        box = map_extents(path)
        if box:
            result.append(box)
    return result


def find_space(width: int, height: int,
               occupied: list[tuple[int, int, int, int]],
               limit: int = 400,
               margin: int = 1,
               include_vanilla: bool = True) -> list[tuple[int, int]]:
    """Return free (x, y) top-left cells for a width x height block."""
    if include_vanilla:
        occupied = [*occupied, VANILLA_BOX]
    free = []
    for y in range(0, limit - height):
        for x in range(0, limit - width):
            block = (x - margin, y - margin, x + width + margin, y + height + margin)
            if any(not (block[2] <= a or block[0] > c or
                        block[3] <= b or block[1] > d)
                   for a, b, c, d in occupied):
                continue
            free.append((x, y))
            if len(free) >= 20:
                return free
    return free
