#!/usr/bin/env python3
"""Build one SoD2-inspired region with named bases/landmarks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pzmapstudio.scene import Scene
from pzmapstudio.worlded import export_scene_map

ORIGINS = {
    "Meagher Valley": (139, 0),
    "Drucker County": (139, 26),
    "Cascade Hills": (139, 52),
    "Providence Ridge": (139, 78),
}


def road(scene: Scene, x1: int, y1: int, x2: int, y2: int, width: int = 28) -> None:
    steps = max(abs(x2 - x1), abs(y2 - y1)) // max(1, width // 2)
    for i in range(steps + 1):
        t = i / max(1, steps)
        x = int(x1 + (x2 - x1) * t)
        y = int(y1 + (y2 - y1) * t)
        px = max(0, min(scene.width - width, x - width // 2))
        py = max(0, min(scene.height - width, y - width // 2))
        scene.paint("roads", px, py, width, width, "asphalt")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", required=True, choices=sorted(ORIGINS))
    parser.add_argument("--out", default="/home/j0schi/SteamLibrary/steamapps/common/ProjectZomboid/work/KnoxMap-dev/dist/sod2-expansion/common/media/maps")
    parser.add_argument("--manifest", default="sod2-buildings.json")
    args = parser.parse_args()
    data = json.loads(Path(args.manifest).read_text())[args.map]
    scene = Scene(args.map, 6400, 6656)
    road(scene, 0, 620, 6400, 620)
    road(scene, 0, 3200, 6400, 3200)
    road(scene, 0, 6100, 6400, 6100)
    road(scene, 620, 0, 620, 6656)
    road(scene, 3000, 0, 3000, 6656)
    road(scene, 5900, 0, 5900, 6656)
    for item in data["bases"]:
        scene.apply({"op": "build_typed", "kind": item["kind"],
                     "x": item["x"], "y": item["y"], "w": item["w"], "h": item["h"],
                     "floors": item.get("floors", 1), "name": item["name"]})
    scene.apply({"op": "add_spawn", "x": 3200, "y": 3300})
    scene.auto_roof_access(min_area=150, kind="stairs")
    template = Path("examples") / f"sod2-{args.map.replace(' ', '-').lower()}.json"
    template.write_text(json.dumps(scene.to_dict(), indent=1), encoding="utf-8")
    cx, cy = ORIGINS[args.map]
    export_scene_map(scene, Path(args.out) / args.map, cx, cy)
    print(args.map, "buildings", len(scene.buildings), "cells", 25 * 26)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
