"""Minimal WorldEd-style writer: rooms/buildings + walls/doors in compiled cells.

This is deliberately small and experimental. It writes a 256-tile cell with:
- a real LOTH header containing rooms and buildings;
- a LOTP pack with a room id and multiple tile names per square.

Wall/door tile choices are generic B42 names; visual orientation and exact
multi-tile placement still need the full WorldEd bridge.
"""
from __future__ import annotations

import math
import struct
from pathlib import Path

from .pzlot import CELL, CHUNKS, CHUNK
from .scene import Scene

GRASS = "floors_exterior_natural_01_16"
ROAD = "floors_exterior_street_01_16"
PAVEMENT = "floors_exterior_street_01_0"
FLOOR = "floors_interior_carpet_01_1"
WALL = "walls_commercial_01_48"
DOOR = "fixtures_doors_01_0"
STAIR = "fixtures_stairs_01_0"


def _tile_for(scene: Scene, x: int, y: int, z: int) -> list[str]:
    tiles: list[str] = []
    if (x, y) in scene.layers["floors"]:
        tiles.append(FLOOR)
    if (x, y) in scene.layers["walls"]:
        tiles.append(WALL)
    obj = scene.layers["objects"].get((x, y), "")
    if obj in ("door", "inner-door"):
        tiles.append(DOOR)
    elif obj.startswith("building:"):
        pass
    elif obj:
        tiles.append(obj)
    if any(stair.x == x and stair.y == y and stair.z == z for stair in scene.stairs):
        tiles.append(STAIR)
    if (x, y) in scene.layers["roads"]:
        tiles.append(ROAD)
    elif (x, y) in scene.layers["sidewalks"]:
        tiles.append(PAVEMENT)
    elif not tiles:
        tiles.append(GRASS)
    return tiles


def export_scene_cell(scene: Scene, out_dir: str | Path, cell_x: int, cell_y: int,
                      origin_x: int = 0, origin_y: int = 0,
                      scene_cell_x: int | None = None,
                      scene_cell_y: int | None = None) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    scx = cell_x if scene_cell_x is None else scene_cell_x
    scy = cell_y if scene_cell_y is None else scene_cell_y
    # room rectangles local to this cell
    rooms: list[tuple[str, int, list[tuple[int, int, int, int]]]] = []
    buildings: list[list[int]] = []
    room_for_square: dict[tuple[int, int, int], int] = {}
    for building in scene.buildings.values():
        ids: list[int] = []
        for z, floor in sorted(building.floors.items()):
            for room in floor.rooms:
                rx = room.x - scx * CELL
                ry = room.y - scy * CELL
                if rx + room.w <= 0 or ry + room.h <= 0 or rx >= CELL or ry >= CELL:
                    continue
                rect = (max(0, rx), max(0, ry),
                        min(CELL, rx + room.w) - max(0, rx),
                        min(CELL, ry + room.h) - max(0, ry))
                if rect[2] <= 0 or rect[3] <= 0:
                    continue
                room_id = len(rooms)
                rooms.append((room.kind or "room", z, [rect]))
                ids.append(room_id)
                for yy in range(rect[1], rect[1] + rect[3]):
                    for xx in range(rect[0], rect[0] + rect[2]):
                        room_for_square[(xx, yy, z)] = room_id + 1
        if ids:
            buildings.append(ids)
    names = [GRASS, ROAD, PAVEMENT, FLOOR, WALL, DOOR, STAIR]
    for tile in scene.layers["objects"].values():
        if tile not in names and not tile.startswith("building:"):
            names.append(tile)
    high = max([z for _, z, _ in rooms] + [0])
    header = bytearray(b"LOTH")
    header += struct.pack("<i", 1)
    header += struct.pack("<i", len(names))
    for name in names:
        header += name.encode("latin-1") + b"\n"
    header += struct.pack("<4i", 8, 8, 0, max(1, high))
    header += struct.pack("<i", len(rooms))
    for name, z, rects in rooms:
        header += name.encode("latin-1", errors="replace") + b"\n"
        header += struct.pack("<2i", z, len(rects))
        for rect in rects:
            header += struct.pack("<4i", *rect)
        header += struct.pack("<i", 0)  # room objects
    header += struct.pack("<i", len(buildings))
    for ids in buildings:
        header += struct.pack("<i", len(ids))
        header += struct.pack(f"<{len(ids)}i", *ids)
    (out / f"{cell_x}_{cell_y}.lotheader").write_bytes(bytes(header))

    name_id = {name: i for i, name in enumerate(names)}
    chunks: list[bytes] = []
    for cx in range(CHUNKS):
        for cy in range(CHUNKS):
            chunk = bytearray()
            for z in range(0, max(1, high) + 1):
                for sx in range(CHUNK):
                    for sy in range(CHUNK):
                        gx = scx * CELL + cx * CHUNK + sx
                        gy = scy * CELL + cy * CHUNK + sy
                        tiles = _tile_for(scene, gx - origin_x, gy - origin_y, z)
                        ids = [name_id.get(t, 0) for t in tiles]
                        room = room_for_square.get((cx * CHUNK + sx, cy * CHUNK + sy, z), 0)
                        chunk += struct.pack("<i", 1 + len(ids))
                        chunk += struct.pack("<i", room)
                        chunk += struct.pack(f"<{len(ids)}i", *ids)
            chunks.append(bytes(chunk))
    base = 4 + 4 + 4 + CHUNKS * CHUNKS * 8
    offsets = []
    position = base
    for chunk in chunks:
        offsets.append(position)
        position += len(chunk)
    pack = bytearray(b"LOTP")
    pack += struct.pack("<i", 1)
    pack += struct.pack("<i", CHUNKS * CHUNKS)
    pack += struct.pack(f"<{CHUNKS * CHUNKS}q", *offsets)
    for chunk in chunks:
        pack += chunk
    (out / f"world_{cell_x}_{cell_y}.lotpack").write_bytes(bytes(pack))
    (out / "map.info").write_text(
        f"title={scene.name}\nlots=Muldraugh, KY\nfixed2x=true\n", encoding="utf-8")
    return out


def _spawn_lua(scene: Scene, origin_x: int = 0, origin_y: int = 0) -> str:
    lines = ["function SpawnPoints()", "  return {", "    unemployed = {"]
    for spawn in scene.spawns:
        lines.append(f"      {{ posX = {spawn.x + origin_x}, posY = {spawn.y + origin_y}, posZ = 0 }},")
    lines += ["    },", "  }", "end", ""]
    return "\n".join(lines)


def export_scene_map(scene: Scene, out_dir: str | Path,
                     cell_x: int = 0, cell_y: int = 0,
                     origin_x: int = 0, origin_y: int = 0) -> Path:
    """Export every cell covering the scene, with rooms/buildings."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cells_x = max(1, math.ceil(scene.width / CELL))
    cells_y = max(1, math.ceil(scene.height / CELL))
    for local_cx in range(cells_x):
        for local_cy in range(cells_y):
            export_scene_cell(scene, out, cell_x + local_cx, cell_y + local_cy,
                              origin_x, origin_y, local_cx, local_cy)
    (out / "map.info").write_text(
        f"title={scene.name}\nlots=Muldraugh, KY\nfixed2x=true\n", encoding="utf-8")
    (out / "spawnpoints.lua").write_text(_spawn_lua(scene, cell_x * CELL, cell_y * CELL), encoding="utf-8")
    (out / "objects.lua").write_text("function getObjectList()\n    return {}\nend\n",
                                     encoding="utf-8")
    return out
