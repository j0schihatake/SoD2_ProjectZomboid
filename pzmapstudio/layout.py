"""Audit map-cell placement: overlaps, gaps, connectivity and vanilla contact."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

VANILLA_CELLS = {(x, y) for x in range(0, 78) for y in range(0, 63)}


def read_cells(map_dir: str | Path) -> set[tuple[int, int]]:
    cells = set()
    for header in Path(map_dir).glob("*.lotheader"):
        parts = header.stem.split("_")
        try:
            cells.add((int(parts[-2]), int(parts[-1])))
        except (ValueError, IndexError):
            continue
    return cells


def audit_layout(root: str | Path) -> dict:
    root = Path(root)
    maps = {path.name: read_cells(path) for path in root.iterdir() if path.is_dir()}
    owners: dict[tuple[int, int], list[str]] = defaultdict(list)
    for name, cells in maps.items():
        for cell in cells:
            owners[cell].append(name)
    overlaps = {key: names for key, names in owners.items() if len(names) > 1}
    extents = {}
    for name, cells in maps.items():
        if cells:
            extents[name] = [min(x for x, _ in cells), min(y for _, y in cells),
                             max(x for x, _ in cells), max(y for _, y in cells)]
    # Connectivity of each map's cells plus its contact with vanilla.
    contact_vanilla = {}
    contact_other = {}
    all_cells = set()
    for cells in maps.values():
        all_cells |= cells
    for name, cells in maps.items():
        touch = any((x + dx, y + dy) in VANILLA_CELLS
                    for x, y in cells for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        contact_vanilla[name] = touch
        other = False
        for (x, y) in cells:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbor = (x + dx, y + dy)
                for other_name, other_cells in maps.items():
                    if other_name != name and neighbor in other_cells:
                        other = True
                        break
                if other:
                    break
            if other:
                break
        contact_other[name] = other
    # Connectivity through maps and vanilla.
    graph = {name: set() for name in maps}
    names = list(maps)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if any((x + dx, y + dy) in maps[b]
                   for x, y in maps[a] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                graph[a].add(b)
                graph[b].add(a)
    direct = {name for name, touch in contact_vanilla.items() if touch}
    seen = set(direct)
    stack = list(direct)
    while stack:
        node = stack.pop()
        for neighbor in graph.get(node, ()):
            if neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    return {
        "maps": {name: {"cells": len(cells), "extents": extents.get(name)}
                 for name, cells in maps.items()},
        "duplicate_cells": {f"{x}_{y}": owners[(x, y)]
                            for (x, y) in sorted(overlaps)},
        "duplicate_count": len(overlaps),
        "vanilla_contact": contact_vanilla,
        "contact_with_other_map": contact_other,
        "connected_to_vanilla": {name: name in seen for name in maps},
        "unconnected_maps": sorted(set(maps) - seen),
    }
