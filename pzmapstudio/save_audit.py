"""Estimate the PZ map_meta.bin state a compiled map will write."""
from __future__ import annotations

from pathlib import Path

from .pzlot import read_header_full

META_CELL = 8
META_ROOM = 10
META_BUILDING = 23
SAVE_BUFFER = 10_485_760
EMPTY_GRID_RESERVE = 501 * 501 * META_CELL
KNOX_COUNTY_META = 1_160_348


def audit_map_root(root: str | Path) -> dict:
    """Audit all map folders that share one world save buffer."""
    root = Path(root)
    maps = {}
    total = {"cells": 0, "rooms": 0, "buildings": 0, "state_bytes": 0}
    for path in sorted(root.iterdir()):
        if not path.is_dir() or not list(path.glob("*.lotheader")):
            continue
        report = audit_map_save(path)
        maps[path.name] = report
        for key in total:
            total[key] += report[key]
    total["world_reserve_bytes"] = EMPTY_GRID_RESERVE + KNOX_COUNTY_META
    total["total_with_world_bytes"] = total["state_bytes"] + total["world_reserve_bytes"]
    total["buffer_bytes"] = SAVE_BUFFER
    total["fraction"] = round(total["total_with_world_bytes"] / SAVE_BUFFER, 4)
    total["warning"] = total["total_with_world_bytes"] > SAVE_BUFFER * 0.9
    return {"maps": maps, "combined": total}


def audit_map_save(map_dir: str | Path) -> dict:
    path = Path(map_dir)
    cells = rooms = buildings = 0
    for header in path.glob("*.lotheader"):
        cells += 1
        try:
            _h, room_list, building_list = read_header_full(header)
        except Exception:
            continue
        rooms += len(room_list)
        buildings += len(building_list)
    estimate = cells * META_CELL + rooms * META_ROOM + buildings * META_BUILDING
    total = estimate + EMPTY_GRID_RESERVE + KNOX_COUNTY_META
    return {
        "map": str(path),
        "cells": cells,
        "rooms": rooms,
        "buildings": buildings,
        "state_bytes": estimate,
        "world_reserve_bytes": EMPTY_GRID_RESERVE + KNOX_COUNTY_META,
        "total_with_world_bytes": total,
        "buffer_bytes": SAVE_BUFFER,
        "fraction": round(total / SAVE_BUFFER, 4),
        "warning": total > SAVE_BUFFER * 0.9,
        "estimate": "conservative-upper-bound; actual map_meta only grew to 3.46 MB in a tested save",
    }
