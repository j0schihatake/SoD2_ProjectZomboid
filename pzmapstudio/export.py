"""Export a scene as a PZ-oriented bundle and a Tiled preview map."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from .pzlot import rewrite_cell, write_cell
from .scene import Scene


def _spawn_lua(scene: Scene) -> str:
    grouped: dict[str, list] = defaultdict(list)
    for spawn in scene.spawns:
        grouped[spawn.profession or "unemployed"].append(spawn)
    lines = ["function SpawnPoints()", "  return {"]
    for profession, spawns in sorted(grouped.items()):
        lines.append(f"    {profession} = {{")
        for spawn in spawns:
            lines.append(
                f"      {{ posX = {spawn.x}, posY = {spawn.y}, posZ = {spawn.z} }},"
            )
        lines.append("    },")
    lines.extend(["  }", "end", ""])
    return "\n".join(lines)


def _objects_lua(scene: Scene) -> str:
    lines = ["function getObjects()", "  local objects = {}"]
    for fence in scene.fences:
        lines.append(
            f"  table.insert(objects, {{name='{fence.kind}', "
            f"x={fence.x}, y={fence.y}, length={fence.length}, axis='{fence.axis}', "
            f"type='Fence'}})"
        )
    for stair in scene.stairs:
        lines.append(
            f"  table.insert(objects, {{name='{stair.kind}', "
            f"x={stair.x}, y={stair.y}, z={stair.z}, toZ={stair.to_z}, "
            f"type='RoofAccess'}})"
        )
    for story in scene.stories:
        lines.append(
            f"  table.insert(objects, {{name='{story.name}', "
            f"x={story.x}, y={story.y}, w={story.w}, h={story.h}, "
            f"type='Story'}})"
        )
    for building in scene.buildings.values():
        lines.append(
            f"  table.insert(objects, {{name='{building.name}', "
            f"x={building.x}, y={building.y}, w={building.w}, h={building.h}, "
            f"type='Building'}})"
        )
        if building.outline:
            points = ";".join(f"{x},{y}" for x, y in building.outline)
            lines.append(f"  table.insert(objects, {{name='{building.name}', "
                         f"points='{points}', type='Footprint'}})")
    lines.extend(["  return objects", "end", ""])
    return "\n".join(lines)


def export_bundle(scene: Scene, out_dir: str | Path) -> Path:
    """Write a portable scene bundle.

    It contains the editable scene plus PZ metadata and spawn/object Lua. It is
    not a compiled map; a PZ compiler adapter still has to turn this into lots.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    scene.save(out / "scene.json")
    (out / "map.info").write_text(
        f"title={scene.name}\n"
        "lots=Muldraugh, KY\n"
        "fixed2x=true\n"
        "description=Editable PZMapStudio scene. Terrain cells are not compiled yet.\n",
        encoding="utf-8",
    )
    (out / "spawnpoints.lua").write_text(_spawn_lua(scene), encoding="utf-8")
    (out / "objects.lua").write_text(_objects_lua(scene), encoding="utf-8")
    (out / "pzmapstudio.json").write_text(
        json.dumps({"format": "pzmapstudio-bundle", "version": 1,
                    "stats": scene.stats()}, indent=2),
        encoding="utf-8",
    )
    return out


def export_pz_region(scene: Scene, out_dir: str | Path,
                     cell_x: int = 0, cell_y: int = 0,
                     fallback: str = "grass") -> Path:
    """Write a terrain-only PZ map folder for a scene rectangle.

    This is a real .lotheader/.lotpack export, not a bundle. It writes one
    level, no rooms/buildings, and is intended for round-tripping terrain and
    roads before the WorldEd building bridge is complete.
    """
    import math
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cells_x = max(1, math.ceil(scene.width / 256))
    cells_y = max(1, math.ceil(scene.height / 256))
    for local_cx in range(cells_x):
        for local_cy in range(cells_y):
            tiles = {}
            for lx in range(256):
                for ly in range(256):
                    sx = local_cx * 256 + lx
                    sy = local_cy * 256 + ly
                    if sx >= scene.width or sy >= scene.height:
                        continue
                    tile = (scene.layers["roads"].get((sx, sy))
                            or scene.layers["sidewalks"].get((sx, sy))
                            or scene.layers["water"].get((sx, sy))
                            or scene.layers["terrain"].get((sx, sy))
                            or fallback)
                    tiles[(lx, ly)] = tile
            write_cell(out, cell_x + local_cx, cell_y + local_cy, tiles, fallback)
    (out / "map.info").write_text(
        f"title={scene.name}\nlots=Muldraugh, KY\nfixed2x=true\n"
        "description=Terrain decoded and exported by PZMapStudio.\n",
        encoding="utf-8",
    )
    (out / "spawnpoints.lua").write_text(_spawn_lua(scene), encoding="utf-8")
    (out / "objects.lua").write_text(_objects_lua(scene), encoding="utf-8")
    return out


def apply_scene_roads(source_map: str | Path, scene: Scene,
                      out_dir: str | Path, origin_x: int, origin_y: int) -> Path:
    """Rewrite roads/sidewalks in real cells while preserving their headers.

    ``origin_x``/``origin_y`` are the absolute compiled-tile coordinates of
    scene tile (0, 0). Existing room and building metadata is copied verbatim;
    only the road/sidewalk overrides are applied.
    """
    source = Path(source_map)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    overrides: dict[tuple[int, int, int], list[str]] = {}
    for layer in ("roads", "sidewalks"):
        for (lx, ly), tile in scene.layers[layer].items():
            overrides[(origin_x + lx, origin_y + ly, 0)] = [tile]
    x0, y0 = origin_x, origin_y
    x1, y1 = origin_x + scene.width, origin_y + scene.height
    cells = sorted({(gx // 256, gy // 256)
                    for gx, gy, _z in overrides})
    for cx, cy in cells:
        cell_overrides = {k: v for k, v in overrides.items()
                          if k[0] // 256 == cx and k[1] // 256 == cy}
        rewrite_cell(source, out, cx, cy, cell_overrides)
    for name in ("map.info", "spawnpoints.lua", "objects.lua"):
        source_file = source / name
        if source_file.exists():
            (out / name).write_bytes(source_file.read_bytes())
    return out


def apply_scene_objects(source_map: str | Path, scene: Scene,
                        out_dir: str | Path, origin_x: int, origin_y: int,
                        layer: str = "objects") -> Path:
    """Rewrite one object layer in real cells while copying headers verbatim."""
    source = Path(source_map)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    overrides: dict[tuple[int, int, int], list[str]] = {}
    for (lx, ly), tile in scene.layers[layer].items():
        overrides[(origin_x + lx, origin_y + ly, 0)] = [tile]
    cells = sorted({(gx // 256, gy // 256) for gx, gy, _z in overrides})
    for cx, cy in cells:
        cell_overrides = {k: v for k, v in overrides.items()
                          if k[0] // 256 == cx and k[1] // 256 == cy}
        rewrite_cell(source, out, cx, cy, cell_overrides)
    for name in ("map.info", "spawnpoints.lua", "objects.lua"):
        source_file = source / name
        if source_file.exists():
            (out / name).write_bytes(source_file.read_bytes())
    return out


def export_tmx(scene: Scene, path: str | Path) -> Path:
    """Write a small Tiled TMX preview (not a PZ lot pack)."""
    root = ET.Element("map", {
        "version": "1.10", "tiledversion": "1.10.2",
        "orientation": "orthogonal", "renderorder": "right-down",
        "width": str(scene.width), "height": str(scene.height),
        "tilewidth": "1", "tileheight": "1", "infinite": "0",
    })
    ET.SubElement(root, "tileset", {
        "firstgid": "1", "name": "terrain", "tilewidth": "1",
        "tileheight": "1", "tilecount": "5", "columns": "5",
    })
    layer = ET.SubElement(root, "layer", {
        "id": "1", "name": "terrain", "width": str(scene.width),
        "height": str(scene.height),
    })
    data = ET.SubElement(layer, "data", {"encoding": "csv"})
    palette = {"grass": 1, "forest": 2, "farm": 3, "water": 4, "sand": 5}
    rows = []
    terrain = scene.layers["terrain"]
    for y in range(scene.height):
        row = []
        for x in range(scene.width):
            row.append(str(palette.get(terrain.get((x, y), "grass"), 1)))
        rows.append(",".join(row))
    data.text = ",\n".join(rows)
    objects = ET.SubElement(root, "objectgroup", {"id": "2", "name": "buildings"})
    for building in scene.buildings.values():
        ET.SubElement(objects, "object", {
            "id": str(len(objects) + 1), "name": building.name,
            "x": str(building.x), "y": str(building.y),
            "width": str(building.w), "height": str(building.h),
        })
    spawn_group = ET.SubElement(root, "objectgroup", {"id": "3", "name": "spawns"})
    for spawn in scene.spawns:
        ET.SubElement(spawn_group, "object", {
            "id": str(len(spawn_group) + 1), "name": spawn.profession,
            "x": str(spawn.x), "y": str(spawn.y), "point": "1",
        })
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path
