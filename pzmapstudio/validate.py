"""Validate a compiled map folder before packaging or publishing."""
from __future__ import annotations

import re
from pathlib import Path

from .pzlot import read_header_full
from .save_audit import audit_map_save

SPAWN = re.compile(r"posX\s*=\s*(-?\d+),\s*posY\s*=\s*(-?\d+)")


def validate_map(map_dir: str | Path) -> dict:
    path = Path(map_dir)
    errors: list[str] = []
    warnings: list[str] = []
    cells = []
    for header in sorted(path.glob("*.lotheader")):
        parts = header.stem.split("_")
        try:
            cx, cy = int(parts[-2]), int(parts[-1])
        except (ValueError, IndexError):
            errors.append(f"bad cell name: {header.name}")
            continue
        cells.append((cx, cy))
        try:
            read_header_full(header)
        except Exception as error:
            errors.append(f"unreadable header {header.name}: {error}")
        pack = path / f"world_{cx}_{cy}.lotpack"
        if not pack.exists():
            errors.append(f"missing lotpack for {cx}_{cy}")
    if not cells:
        errors.append("no .lotheader cells")
    if not (path / "map.info").exists():
        warnings.append("map.info is missing")
    spawns = 0
    spawn_file = path / "spawnpoints.lua"
    if spawn_file.exists():
        for x, y in SPAWN.findall(spawn_file.read_text(errors="ignore")):
            spawns += 1
            if (int(x) // 256, int(y) // 256) not in set(cells):
                errors.append(f"spawn outside cells: {x},{y}")
    else:
        warnings.append("spawnpoints.lua is missing")
    report = audit_map_save(path)
    if report["warning"]:
        warnings.append("save-state estimate is above 90%; verify with a real save")
    return {
        "map": str(path),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "cells": len(cells),
        "spawns": spawns,
        "save_state": report,
    }
