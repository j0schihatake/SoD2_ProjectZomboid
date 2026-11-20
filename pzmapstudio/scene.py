"""Sparse, command-driven map scene.

The scene is deliberately independent of Project Zomboid's binary lot format.
It stores tiles, buildings, furniture and spawn markers as plain data, so an
agent can edit it through JSON commands and a UI can render the same state.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LAYERS = ("terrain", "roads", "sidewalks", "water", "floors", "walls", "objects", "zones")


class SceneError(ValueError):
    pass


@dataclass
class Furniture:
    kind: str
    x: int
    y: int
    z: int = 0
    rotation: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "x": self.x, "y": self.y, "z": self.z,
                "rotation": self.rotation}


@dataclass
class Room:
    x: int
    y: int
    w: int
    h: int
    kind: str = "room"

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h, "kind": self.kind}


@dataclass
class Floor:
    z: int
    rooms: list[Room] = field(default_factory=list)
    furniture: list[Furniture] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"z": self.z, "rooms": [r.to_dict() for r in self.rooms],
                "furniture": [f.to_dict() for f in self.furniture]}


@dataclass
class Building:
    id: str
    name: str
    x: int
    y: int
    w: int
    h: int
    floors: dict[int, Floor] = field(default_factory=dict)
    outline: list[tuple[int, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "x": self.x, "y": self.y,
            "w": self.w, "h": self.h,
            "outline": [list(point) for point in self.outline],
            "floors": {str(k): v.to_dict() for k, v in sorted(self.floors.items())},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Building":
        floors = {}
        for key, value in data.get("floors", {}).items():
            floor = Floor(z=int(value.get("z", key)))
            floor.rooms = [Room(**room) for room in value.get("rooms", [])]
            floor.furniture = [Furniture(**item) for item in value.get("furniture", [])]
            floors[floor.z] = floor
        return cls(
            id=str(data["id"]), name=str(data.get("name", data["id"])),
            x=int(data["x"]), y=int(data["y"]), w=int(data["w"]), h=int(data["h"]),
            floors=floors,
            outline=[(int(x), int(y)) for x, y in data.get("outline", [])],
        )


@dataclass
class Spawn:
    x: int
    y: int
    z: int = 0
    profession: str = "unemployed"

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "z": self.z,
                "profession": self.profession}


@dataclass
class Reference:
    title: str
    url: str = ""
    path: str = ""
    building: str = ""
    lat: float | None = None
    lon: float | None = None
    notes: str = ""
    kind: str = "photo"

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "url": self.url, "path": self.path,
                "building": self.building, "lat": self.lat, "lon": self.lon,
                "notes": self.notes, "kind": self.kind}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Reference":
        return cls(title=str(data.get("title", "")), url=str(data.get("url", "")),
                   path=str(data.get("path", "")), building=str(data.get("building", "")),
                   lat=data.get("lat"), lon=data.get("lon"),
                   notes=str(data.get("notes", "")), kind=str(data.get("kind", "photo")))


@dataclass
class Fence:
    x: int
    y: int
    length: int
    axis: str = "x"
    kind: str = "picket"
    gate: bool = False
    tile: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "length": self.length,
                "axis": self.axis, "kind": self.kind, "gate": self.gate,
                "tile": self.tile}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Fence":
        return cls(x=int(data["x"]), y=int(data["y"]), length=int(data["length"]),
                   axis=str(data.get("axis", "x")), kind=str(data.get("kind", "picket")),
                   gate=bool(data.get("gate", False)), tile=str(data.get("tile", "")))


@dataclass
class Stair:
    building: str
    x: int
    y: int
    z: int
    to_z: int
    kind: str = "stairs"

    def to_dict(self) -> dict[str, Any]:
        return {"building": self.building, "x": self.x, "y": self.y,
                "z": self.z, "to_z": self.to_z, "kind": self.kind}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Stair":
        return cls(building=str(data["building"]), x=int(data["x"]), y=int(data["y"]),
                   z=int(data.get("z", 0)), to_z=int(data.get("to_z", 1)),
                   kind=str(data.get("kind", "stairs")))


@dataclass
class StorySite:
    id: str
    kind: str
    name: str
    x: int
    y: int
    w: int = 1
    h: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "name": self.name,
                "x": self.x, "y": self.y, "w": self.w, "h": self.h}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StorySite":
        return cls(id=str(data["id"]), kind=str(data.get("kind", "story")),
                   name=str(data.get("name", "story")), x=int(data["x"]),
                   y=int(data["y"]), w=int(data.get("w", 1)), h=int(data.get("h", 1)))


def _point_in_polygon(x: float, y: float, points: list[tuple[int, int]]) -> bool:
    inside = False
    j = len(points) - 1
    for i, (xi, yi) in enumerate(points):
        xj, yj = points[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _line_points(x0: int, y0: int, x1: int, y1: int):
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx - dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


class Scene:
    """Editable map scene with undo/redo."""

    def __init__(self, name: str = "Untitled", width: int = 512, height: int = 512):
        if width <= 0 or height <= 0:
            raise SceneError("width and height must be positive")
        self.name = name
        self.width = int(width)
        self.height = int(height)
        self.layers: dict[str, dict[tuple[int, int], str]] = {name: {} for name in LAYERS}
        self.buildings: dict[str, Building] = {}
        self.spawns: list[Spawn] = []
        self.stories: list[StorySite] = []
        self.stairs: list[Stair] = []
        self.fences: list[Fence] = []
        self.references: list[Reference] = []
        self._history: list[str] = []
        self._redo: list[str] = []

    # ------------------------------------------------------------------ state
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "layers": {
                name: [{"x": x, "y": y, "tile": tile}
                       for (x, y), tile in sorted(cells.items())]
                for name, cells in self.layers.items()
            },
            "buildings": [b.to_dict() for b in self.buildings.values()],
            "spawns": [s.to_dict() for s in self.spawns],
            "stories": [s.to_dict() for s in self.stories],
            "stairs": [s.to_dict() for s in self.stairs],
            "fences": [s.to_dict() for s in self.fences],
            "references": [r.to_dict() for r in self.references],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scene":
        scene = cls(
            name=str(data.get("name", "Untitled")),
            width=int(data.get("width", 512)),
            height=int(data.get("height", 512)),
        )
        for layer, cells in data.get("layers", {}).items():
            if layer not in scene.layers:
                scene.layers[layer] = {}
            for item in cells:
                scene.layers[layer][(int(item["x"]), int(item["y"]))] = str(item["tile"])
        scene.buildings = {
            str(item["id"]): Building.from_dict(item)
            for item in data.get("buildings", [])
        }
        scene.spawns = [Spawn(**item) for item in data.get("spawns", [])]
        scene.stories = [StorySite.from_dict(item) for item in data.get("stories", [])]
        scene.stairs = [Stair.from_dict(item) for item in data.get("stairs", [])]
        scene.fences = [Fence.from_dict(item) for item in data.get("fences", [])]
        scene.references = [Reference.from_dict(item) for item in data.get("references", [])]
        scene._history = []
        scene._redo = []
        return scene

    def check_rect(self, x: int, y: int, w: int, h: int) -> None:
        if w <= 0 or h <= 0:
            raise SceneError("rectangle must have positive width and height")
        if x < 0 or y < 0 or x + w > self.width or y + h > self.height:
            raise SceneError(
                f"rectangle {x},{y},{w},{h} is outside scene {self.width}x{self.height}"
            )

    # --------------------------------------------------------------- commands
    def apply(self, command: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(command, dict) or "op" not in command:
            raise SceneError("command must be an object with an 'op' field")
        before = json.dumps(self.to_dict(), sort_keys=True)
        op = str(command["op"])
        result: dict[str, Any] = {"op": op, "ok": True}

        if op == "paint":
            result.update(self.paint(
                layer=str(command.get("layer", "terrain")),
                x=int(command["x"]), y=int(command["y"]),
                w=int(command["w"]), h=int(command["h"]),
                tile=str(command["tile"]),
            ))
        elif op == "erase":
            result.update(self.erase(
                layer=str(command.get("layer", "terrain")),
                x=int(command["x"]), y=int(command["y"]),
                w=int(command["w"]), h=int(command["h"]),
            ))
        elif op == "build_footprint":
            points = [(int(p[0]), int(p[1])) for p in command["points"]]
            result.update(self.build_footprint(
                points=points, floors=int(command.get("floors", 1)),
                rooms=int(command.get("rooms", 4)),
                furnish=bool(command.get("furnish", True)),
                name=str(command.get("name", "")),
            ))
        elif op == "build_typed":
            result.update(self.build_typed(
                kind=str(command.get("kind", "house")),
                x=int(command["x"]), y=int(command["y"]),
                w=int(command["w"]), h=int(command["h"]),
                floors=int(command.get("floors", 1)),
                furnish=bool(command.get("furnish", True)),
                name=str(command.get("name", "")),
            ))
        elif op == "build_house":
            result.update(self.build_house(
                x=int(command["x"]), y=int(command["y"]),
                w=int(command["w"]), h=int(command["h"]),
                floors=int(command.get("floors", 1)),
                rooms=int(command.get("rooms", 4)),
                furnish=bool(command.get("furnish", True)),
                name=str(command.get("name", "")),
            ))
        elif op == "add_floor":
            result.update(self.add_floor(str(command["building"]), int(command["z"]),
                                         int(command.get("rooms", 4)),
                                         bool(command.get("furnish", True))))
        elif op == "place_furniture":
            result.update(self.place_furniture(
                str(command["building"]), int(command["x"]), int(command["y"]),
                int(command.get("z", 0)), str(command.get("kind", "chair")),
            ))
        elif op == "add_reference":
            result.update(self.add_reference(
                title=str(command.get("title", "reference")),
                url=str(command.get("url", "")),
                path=str(command.get("path", "")),
                building=str(command.get("building", "")),
                lat=command.get("lat"), lon=command.get("lon"),
                notes=str(command.get("notes", "")),
                kind=str(command.get("kind", "photo")),
            ))
        elif op == "remove_reference":
            result.update(self.remove_reference(int(command.get("index", -1))))
        elif op == "clean_roads":
            result.update(self.clean_roads())
        elif op == "auto_roof_access":
            result.update(self.auto_roof_access(
                min_area=int(command.get("min_area", 120)),
                kind=str(command.get("kind", "ladder")),
            ))
        elif op == "art_pass":
            result.update(self.art_pass(
                min_roof_area=int(command.get("min_roof_area", 120)),
                roof_kind=str(command.get("roof_kind", "ladder")),
            ))
        elif op == "clean_interiors":
            result.update(self.clean_interiors())
        elif op == "add_road":
            result.update(self.add_road(
                x=int(command["x"]), y=int(command["y"]),
                w=int(command["w"]), h=int(command["h"]),
                material=str(command.get("material", "asphalt")),
                sidewalk=bool(command.get("sidewalk", True)),
            ))
        elif op == "place_object":
            result.update(self.place_object(
                int(command["x"]), int(command["y"]), str(command["tile"]),
                str(command.get("kind", "object")),
            ))
        elif op == "add_fence":
            result.update(self.add_fence(
                x=int(command["x"]), y=int(command["y"]),
                length=int(command["length"]),
                axis=str(command.get("axis", "x")),
                kind=str(command.get("kind", "picket")),
                gate=bool(command.get("gate", False)),
                tile=str(command.get("tile", "")),
            ))
        elif op == "add_roof_access":
            result.update(self.add_roof_access(
                str(command["building"]), int(command["x"]), int(command["y"]),
                int(command.get("z", 0)), int(command.get("to_z", 1)),
                str(command.get("kind", "stairs")),
            ))
        elif op == "add_story":
            result.update(self.add_story(
                x=int(command["x"]), y=int(command["y"]),
                w=int(command.get("w", 1)), h=int(command.get("h", 1)),
                kind=str(command.get("kind", "story")),
                name=str(command.get("name", "")),
            ))
        elif op == "remove_story":
            result.update(self.remove_story(str(command.get("id", ""))))
        elif op == "add_spawn":
            result.update(self.add_spawn(int(command["x"]), int(command["y"]),
                                         int(command.get("z", 0)),
                                         str(command.get("profession", "unemployed"))))
        elif op == "remove_spawn":
            result.update(self.remove_spawn(int(command["index"])))
        elif op == "undo":
            result.update(self.undo())
        elif op == "redo":
            result.update(self.redo())
        else:
            raise SceneError(f"unknown op: {op}")

        if op not in ("undo", "redo") and isinstance(result, dict):
            self._history.append(before)
            if len(self._history) > 100:
                self._history.pop(0)
            self._redo.clear()
        return result

    def apply_batch(self, commands: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply commands atomically: on error the scene is restored."""
        before = json.dumps(self.to_dict(), sort_keys=True)
        results = []
        try:
            for index, command in enumerate(commands):
                results.append({"index": index, "result": self.apply(command)})
        except Exception:
            restored = Scene.from_dict(json.loads(before))
            history, redo = self._history, self._redo
            self.__dict__.update(restored.__dict__)
            self._history, self._redo = history, redo
            raise
        return {"applied": len(results), "results": results}

    def paint(self, layer: str, x: int, y: int, w: int, h: int, tile: str) -> dict[str, Any]:
        if layer not in self.layers:
            raise SceneError(f"unknown layer: {layer}")
        self.check_rect(x, y, w, h)
        cells = self.layers[layer]
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                cells[(xx, yy)] = tile
        return {"painted": w * h, "layer": layer}

    def erase(self, layer: str, x: int, y: int, w: int, h: int) -> dict[str, Any]:
        if layer not in self.layers:
            raise SceneError(f"unknown layer: {layer}")
        self.check_rect(x, y, w, h)
        cells = self.layers[layer]
        removed = 0
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if (xx, yy) in cells:
                    del cells[(xx, yy)]
                    removed += 1
        return {"erased": removed, "layer": layer}

    def build_typed(self, kind: str, x: int, y: int, w: int, h: int,
                    floors: int = 1, furnish: bool = True,
                    name: str = "") -> dict[str, Any]:
        """Build a named building type with a simple type-specific interior.

        This is still a prototype layout, not a reconstruction of a real plan.
        """
        self.check_rect(x, y, w, h)
        if w < 12 or h < 10:
            raise SceneError("typed building needs at least 12x10 tiles")
        kind = kind.lower()
        allowed = {"house", "church", "courthouse", "school", "clinic", "barn",
                   "warehouse", "shop", "mill", "fair_hall", "base"}
        if kind not in allowed:
            raise SceneError(f"unknown building kind: {kind}")
        building_id = f"{kind}-{len(self.buildings) + 1}"
        building = Building(id=building_id, name=name or building_id,
                            x=x, y=y, w=w, h=h)
        for z in range(max(1, floors)):
            floor = Floor(z=z)
            rooms = self._typed_rooms(kind, x, y, w, h)
            floor.rooms.extend(rooms)
            if furnish:
                floor.furniture.extend(self._typed_furniture(kind, rooms, z))
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    self.layers["floors"][(xx, yy)] = f"floor:{z}"
            for yy in (y, y + h - 1):
                for xx in range(x, x + w):
                    self.layers["walls"][(xx, yy)] = "wall"
            for xx in (x, x + w - 1):
                for yy in range(y, y + h):
                    self.layers["walls"][(xx, yy)] = "wall"
            # main entrance on the south wall
            door = (x + w // 2, y + h - 1)
            self.layers["walls"].pop(door, None)
            self.layers["objects"][door] = "door"
            if kind in {"courthouse", "school", "clinic", "fair_hall", "base"}:
                for door in ((x, y + h // 2), (x + w - 1, y + h // 2)):
                    self.layers["walls"].pop(door, None)
                    self.layers["objects"][door] = "door"
            # simple interior partitions, one door per room
            for room in rooms:
                if room.kind == "entrance":
                    continue
                for xx in range(room.x, room.x + room.w):
                    for yy in (room.y, room.y + room.h - 1):
                        if (xx, yy) not in ((x, y + h - 1), (x + w - 1, y + h - 1)):
                            self.layers["walls"][(xx, yy)] = "wall"
                for yy in range(room.y, room.y + room.h):
                    for xx in (room.x, room.x + room.w - 1):
                        if (xx, yy) not in ((x, y + h - 1), (x + w - 1, y + h - 1)):
                            self.layers["walls"][(xx, yy)] = "wall"
                door = (room.x + room.w // 2, min(y + h - 2, room.y + room.h - 1))
                self.layers["walls"].pop(door, None)
                self.layers["objects"][door] = "inner-door"
            building.floors[z] = floor
        if kind == "base":
            self.add_fence(x + 2, y + 2, w - 4, axis="x", tile="fencing_01_0", gate=True)
            self.add_fence(x + 2, y + h - 3, w - 4, axis="x", tile="fencing_01_0", gate=True)
            self.add_fence(x + 2, y + 2, h - 4, axis="y", tile="fencing_01_0", gate=True)
            self.add_fence(x + w - 3, y + 2, h - 4, axis="y", tile="fencing_01_0", gate=True)
        self.buildings[building_id] = building
        return {"building": building_id, "kind": kind, "floors": len(building.floors),
                "rooms": sum(len(f.rooms) for f in building.floors.values())}

    @staticmethod
    def _typed_rooms(kind: str, x: int, y: int, w: int, h: int) -> list[Room]:
        if kind == "church":
            return [Room(x + 8, y + 16, w - 16, h - 34, "nave"),
                    Room(x + w // 2 - 30, y + 4, 60, 10, "altar"),
                    Room(x + w // 2 - 30, y + h - 14, 60, 10, "vestibule")]
        if kind == "courthouse":
            return [Room(x + 4, y + 4, w - 8, h // 3, "lobby"),
                    Room(x + 4, y + h // 3 + 4, w // 2 - 6, h // 3, "courtroom A"),
                    Room(x + w // 2 + 2, y + h // 3 + 4, w // 2 - 6, h // 3, "courtroom B"),
                    Room(x + 4, y + 2 * h // 3 + 4, w // 2 - 6, h // 3 - 6, "clerk office"),
                    Room(x + w // 2 + 2, y + 2 * h // 3 + 4, w // 2 - 6, h // 3 - 6, "records")]
        if kind == "school":
            rooms = []
            for i in range(3):
                rooms.append(Room(x + 4 + i * (w - 8) // 3, y + 4,
                                  (w - 8) // 3 - 2, h - 12, "classroom"))
            return rooms
        if kind == "clinic":
            return [Room(x + 4, y + 4, w - 8, h // 3, "waiting"),
                    Room(x + 4, y + h // 3 + 4, w // 2 - 6, h // 2, "exam"),
                    Room(x + w // 2 + 2, y + h // 3 + 4, w // 2 - 6, h // 2, "ward")]
        if kind == "base":
            return [Room(x + 12, y + 12, w - 24, h - 50, "compound yard"),
                    Room(x + 16, y + 16, w // 2 - 20, 26, "command"),
                    Room(x + w // 2 + 4, y + 16, w // 2 - 20, 26, "infirmary"),
                    Room(x + 16, y + h - 34, w // 2 - 20, 22, "barracks"),
                    Room(x + w // 2 + 4, y + h - 34, w // 2 - 20, 22, "storage")]
        if kind == "barn":
            return [Room(x + 3, y + 3, w - 6, h - 6, "barn floor"),
                    Room(x + 6, y + 6, w // 2 - 8, h - 12, "stalls")]
        if kind == "warehouse":
            return [Room(x + 3, y + 3, w - 6, h - 6, "warehouse"),
                    Room(x + 5, y + h - 18, w - 10, 12, "loading dock")]
        if kind == "shop":
            return [Room(x + 3, y + 3, w - 6, h // 2, "sales"),
                    Room(x + 3, y + h // 2 + 3, w - 6, h // 2 - 6, "stock")]
        if kind == "mill":
            return [Room(x + 3, y + 3, w - 6, h - 24, "mill floor"),
                    Room(x + 3, y + h - 20, w - 6, 14, "loading dock"),
                    Room(x + w - 34, y + 4, 28, 22, "mill office")]
        if kind == "fair_hall":
            return [Room(x + 4, y + 4, w - 8, h - 18, "exhibition"),
                    Room(x + 4, y + h - 14, 44, 10, "entrance"),
                    Room(x + w - 54, y + h - 14, 50, 10, "stalls")]
        return [Room(x + 3, y + 3, w // 2 - 4, h // 2 - 4, "living"),
                Room(x + w // 2 + 1, y + 3, w // 2 - 4, h // 2 - 4, "kitchen"),
                Room(x + 3, y + h // 2 + 1, w - 6, h // 2 - 4, "bedroom")]

    @staticmethod
    def _typed_furniture(kind: str, rooms: list[Room], z: int) -> list[Furniture]:
        items: list[Furniture] = []
        if kind == "church":
            room = rooms[0]
            center = room.x + room.w // 2
            # two pew blocks with a central aisle
            for row in range(room.y + 6, room.y + room.h - 3, 7):
                for col in range(room.x + 4, center - 6, 7):
                    items.append(Furniture("chair", col, row, z))
                for col in range(center + 6, room.x + room.w - 4, 7):
                    items.append(Furniture("chair", col, row, z))
            items.append(Furniture("table", center, room.y + 2, z))
            items.append(Furniture("lamp", center - 5, room.y + 2, z))
            items.append(Furniture("lamp", center + 5, room.y + 2, z))
            if len(rooms) > 1:
                altar = rooms[1]
                items.append(Furniture("table", altar.x + altar.w // 2, altar.y + 2, z))
        elif kind == "courthouse":
            for room in rooms:
                items.append(Furniture("table", room.x + 2, room.y + 2, z))
                for row in range(room.y + 8, room.y + room.h - 2, 5):
                    for col in range(room.x + 4, room.x + room.w - 3, 5):
                        items.append(Furniture("chair", col, row, z))
        elif kind == "school":
            for room in rooms:
                for row in range(room.y + 4, room.y + room.h - 2, 6):
                    for col in range(room.x + 4, room.x + room.w - 3, 6):
                        items.append(Furniture("chair", col, row, z))
                items.append(Furniture("table", room.x + 2, room.y + 1, z))
        elif kind == "base":
            for room in rooms[1:]:
                items.append(Furniture("table", room.x + 2, room.y + 2, z))
                items.append(Furniture("chair", room.x + 4, room.y + 6, z))
            items.append(Furniture("table", rooms[0].x + rooms[0].w // 2, rooms[0].y + rooms[0].h // 2, z))
        elif kind in {"clinic", "house"}:
            for room in rooms:
                items.append(Furniture("bed", room.x + 1, room.y + 1, z))
                items.append(Furniture("table", room.x + room.w - 3, room.y + room.h - 3, z))
                items.append(Furniture("lamp", room.x + room.w - 2, room.y + 1, z))
        elif kind in {"barn", "warehouse", "mill"}:
            for i in range(6):
                items.append(Furniture("table", rooms[0].x + 3 + i * 6, rooms[0].y + 4, z))
            if len(rooms) > 1:
                for i in range(3):
                    items.append(Furniture("table", rooms[1].x + 3 + i * 5, rooms[1].y + 3, z))
        elif kind == "shop":
            for i in range(6):
                items.append(Furniture("table", rooms[0].x + 2 + i * 5, rooms[0].y + 4, z))
            for i in range(4):
                items.append(Furniture("table", rooms[1].x + 2 + i * 5, rooms[1].y + 2, z))
        elif kind == "fair_hall":
            for row in range(rooms[0].y + 6, rooms[0].y + rooms[0].h - 4, 8):
                for i in range(8):
                    items.append(Furniture("table", rooms[0].x + 3 + i * 6, row, z))
            if len(rooms) > 2:
                for i in range(5):
                    items.append(Furniture("table", rooms[2].x + 2 + i * 4, rooms[2].y + 3, z))
        return items

    def build_house(self, x: int, y: int, w: int, h: int, floors: int = 1,
                    rooms: int = 4, furnish: bool = True, name: str = "") -> dict[str, Any]:
        self.check_rect(x, y, w, h)
        if floors < 1 or floors > 32:
            raise SceneError("floors must be between 1 and 32")
        if w < 6 or h < 6:
            raise SceneError("a house needs at least 6x6 tiles")
        building_id = f"house-{len(self.buildings) + 1}"
        building = Building(
            id=building_id, name=name or building_id,
            x=x, y=y, w=w, h=h,
        )
        for z in range(floors):
            self._add_floor(building, z, rooms, furnish)
        self.buildings[building_id] = building
        self.layers["objects"][(x + w // 2, y + h // 2)] = f"building:{building_id}"
        return {"building": building_id, "floors": floors,
                "furniture": sum(len(f.furniture) for f in building.floors.values())}

    def build_footprint(self, points: list[tuple[int, int]], floors: int = 1,
                        rooms: int = 4, furnish: bool = True,
                        name: str = "") -> dict[str, Any]:
        """Build a building with an arbitrary roof/footprint polygon."""
        if len(points) < 3:
            raise SceneError("a footprint needs at least three points")
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        x, y = min(xs), min(ys)
        w, h = max(xs) - x + 1, max(ys) - y + 1
        self.check_rect(x, y, w, h)
        building_id = f"house-{len(self.buildings) + 1}"
        building = Building(id=building_id, name=name or building_id,
                            x=x, y=y, w=w, h=h, outline=list(points))
        for z in range(max(1, floors)):
            floor = Floor(z=z)
            room_w = max(3, w // 2)
            room_h = max(3, h // 2)
            count = 0
            for ry in range(y, y + h - 2, room_h):
                for rx in range(x, x + w - 2, room_w):
                    if count >= rooms:
                        break
                    cx, cy = rx + room_w / 2, ry + room_h / 2
                    if _point_in_polygon(cx, cy, points):
                        floor.rooms.append(Room(rx, ry, min(room_w, x + w - rx),
                                                min(room_h, y + h - ry)))
                        count += 1
                if count >= rooms:
                    break
            if furnish:
                occupied: set[tuple[int, int]] = set()
                for room in floor.rooms:
                    placements = [("bed", room.x + 1, room.y + 1),
                                  ("table", room.x + room.w - 2, room.y + room.h - 2),
                                  ("chair", room.x + room.w - 3, room.y + room.h - 2),
                                  ("lamp", room.x + room.w - 2, room.y + 1)]
                    for kind, fx, fy in placements:
                        if not _point_in_polygon(fx + 0.5, fy + 0.5, points):
                            continue
                        if (fx, fy) in occupied:
                            continue
                        occupied.add((fx, fy))
                        floor.furniture.append(Furniture(kind=kind, x=fx, y=fy, z=z))
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    if _point_in_polygon(xx + 0.5, yy + 0.5, points):
                        self.layers["floors"][(xx, yy)] = f"floor:{z}"
            # Outline walls and one door on the southern-most edge.
            edges = list(zip(points, points[1:] + points[:1]))
            for (x0, y0), (x1, y1) in edges:
                for xx, yy in _line_points(x0, y0, x1, y1):
                    self.layers["walls"][(xx, yy)] = "wall"
            door_edge = max(edges, key=lambda edge: (edge[0][1] + edge[1][1], edge[0][0]))
            (x0, y0), (x1, y1) = door_edge
            door = ((x0 + x1) // 2, (y0 + y1) // 2)
            self.layers["walls"].pop(door, None)
            self.layers["objects"][door] = "door"
            building.floors[z] = floor
        if kind == "base":
            self.add_fence(x + 2, y + 2, w - 4, axis="x", tile="fencing_01_0", gate=True)
            self.add_fence(x + 2, y + h - 3, w - 4, axis="x", tile="fencing_01_0", gate=True)
            self.add_fence(x + 2, y + 2, h - 4, axis="y", tile="fencing_01_0", gate=True)
            self.add_fence(x + w - 3, y + 2, h - 4, axis="y", tile="fencing_01_0", gate=True)
        self.buildings[building_id] = building
        return {"building": building_id, "points": len(points), "floors": len(building.floors)}

    def add_floor(self, building_id: str, z: int, rooms: int = 4,
                  furnish: bool = True) -> dict[str, Any]:
        building = self.buildings.get(building_id)
        if building is None:
            raise SceneError(f"unknown building: {building_id}")
        if z in building.floors:
            raise SceneError(f"floor {z} already exists in {building_id}")
        self._add_floor(building, int(z), int(rooms), bool(furnish))
        return {"building": building_id, "z": int(z),
                "rooms": len(building.floors[int(z)].rooms)}

    def _add_floor(self, building: Building, z: int, rooms: int, furnish: bool) -> None:
        floor = Floor(z=z)
        rooms = max(1, int(rooms))
        room_w = max(2, building.w // 2)
        room_h = max(2, building.h // 2)
        count = 0
        for ry in range(building.y, building.y + building.h - 2, room_h):
            for rx in range(building.x, building.x + building.w - 2, room_w):
                if count >= rooms:
                    break
                floor.rooms.append(Room(rx, ry, room_w, room_h))
                count += 1
            if count >= rooms:
                break
        # Floor slab and perimeter walls, with a front door gap.
        for yy in range(building.y + 1, building.y + building.h - 1):
            for xx in range(building.x + 1, building.x + building.w - 1):
                self.layers["floors"][(xx, yy)] = f"floor:{z}"
        for xx in range(building.x, building.x + building.w):
            self.layers["walls"][(xx, building.y)] = "wall"
            self.layers["walls"][(xx, building.y + building.h - 1)] = "wall"
        for yy in range(building.y, building.y + building.h):
            self.layers["walls"][(building.x, yy)] = "wall"
            self.layers["walls"][(building.x + building.w - 1, yy)] = "wall"
        door = (building.x + building.w // 2, building.y + building.h - 1)
        self.layers["walls"].pop(door, None)
        self.layers["objects"][door] = "door"

        if furnish:
            occupied: set[tuple[int, int]] = set()
            for index, room in enumerate(floor.rooms):
                placements = []
                if room.w >= 4 and room.h >= 4:
                    placements = [
                        ("bed", room.x + 1, room.y + 1),
                        ("table", room.x + room.w - 2, room.y + room.h - 2),
                        ("chair", room.x + room.w - 3, room.y + room.h - 2),
                        ("kitchen", room.x + 1, room.y + room.h - 2),
                        ("lamp", room.x + room.w - 2, room.y + 1),
                    ]
                elif room.w >= 2 and room.h >= 2:
                    placements = [("lamp", room.x, room.y)]
                for kind, fx, fy in placements:
                    if (fx, fy) in occupied:
                        continue
                    occupied.add((fx, fy))
                    floor.furniture.append(Furniture(kind=kind, x=fx, y=fy, z=z))
        building.floors[z] = floor

    def place_furniture(self, building_id: str, x: int, y: int, z: int = 0,
                        kind: str = "chair") -> dict[str, Any]:
        building = self.buildings.get(building_id)
        if building is None:
            raise SceneError(f"unknown building: {building_id}")
        if z not in building.floors:
            raise SceneError(f"floor {z} does not exist in {building_id}")
        if not (building.x <= x < building.x + building.w and
                building.y <= y < building.y + building.h):
            raise SceneError("furniture must be inside the building footprint")
        furniture = Furniture(kind=kind, x=x, y=y, z=z)
        building.floors[z].furniture.append(furniture)
        return {"placed": kind, "x": x, "y": y, "z": z}

    def add_reference(self, title: str, url: str = "", path: str = "",
                      building: str = "", lat: float | None = None,
                      lon: float | None = None, notes: str = "",
                      kind: str = "photo") -> dict[str, Any]:
        if building and building not in self.buildings:
            raise SceneError(f"unknown building: {building}")
        if kind not in ("photo", "floorplan", "map", "other"):
            raise SceneError(f"unknown reference kind: {kind}")
        self.references.append(Reference(title=title, url=url, path=path,
                                         building=building, lat=lat, lon=lon,
                                         notes=notes, kind=kind))
        return {"reference": len(self.references) - 1, "title": title, "kind": kind}

    def remove_reference(self, index: int) -> dict[str, Any]:
        if not (0 <= index < len(self.references)):
            raise SceneError("reference index out of range")
        del self.references[index]
        return {"removed": index}

    def clean_roads(self) -> dict[str, Any]:
        """Roads and sidewalks take precedence over grass and water."""
        removed = 0
        for layer in ("terrain", "water"):
            cells = self.layers[layer]
            for key in list(cells):
                if key in self.layers["roads"] or key in self.layers["sidewalks"]:
                    del cells[key]
                    removed += 1
        for key in list(self.layers["terrain"]):
            if key in self.layers["sidewalks"]:
                del self.layers["terrain"][key]
                removed += 1
        return {"removed_ground": removed, "roads": len(self.layers["roads"]),
                "sidewalks": len(self.layers["sidewalks"])}

    def auto_roof_access(self, min_area: int = 120,
                         kind: str = "ladder") -> dict[str, Any]:
        """Add one roof route to large buildings that lack one."""
        added = 0
        for building in self.buildings.values():
            if building.w * building.h < min_area:
                continue
            if any(stair.building == building.id for stair in self.stairs):
                continue
            top = max(building.floors) if building.floors else 0
            if top < 1:
                continue
            x = building.x + building.w // 2
            y = building.y
            self.stairs.append(Stair(building=building.id, x=x, y=y, z=0,
                                     to_z=top + 1, kind=kind))
            added += 1
        return {"added": added, "total": len(self.stairs)}

    def art_pass(self, min_roof_area: int = 120,
                 roof_kind: str = "ladder") -> dict[str, Any]:
        interiors = self.clean_interiors()
        roads = self.clean_roads()
        roofs = self.auto_roof_access(min_roof_area, roof_kind)
        return {"interiors": interiors, "roads": roads, "roofs": roofs}

    def clean_interiors(self) -> dict[str, Any]:
        """Remove outdoor ground from building footprints and lay interior floor."""
        removed = 0
        buildings = 0
        for building in self.buildings.values():
            buildings += 1
            for yy in range(building.y, building.y + building.h):
                for xx in range(building.x, building.x + building.w):
                    for layer in ("terrain", "roads", "sidewalks", "water"):
                        if (xx, yy) in self.layers[layer]:
                            del self.layers[layer][(xx, yy)]
                            removed += 1
                    self.layers["floors"][(xx, yy)] = "floor"
        return {"buildings": buildings, "removed_outdoor_tiles": removed}

    def add_road(self, x: int, y: int, w: int, h: int,
                 material: str = "asphalt", sidewalk: bool = True) -> dict[str, Any]:
        self.check_rect(x, y, w, h)
        self.paint("roads", x, y, w, h, material)
        if sidewalk:
            if w >= h:
                if h >= 3:
                    self.paint("sidewalks", x, y, w, 1, "sidewalk")
                    self.paint("sidewalks", x, y + h - 1, w, 1, "sidewalk")
            else:
                if w >= 3:
                    self.paint("sidewalks", x, y, 1, h, "sidewalk")
                    self.paint("sidewalks", x + w - 1, y, 1, h, "sidewalk")
        return {"road": material, "x": x, "y": y, "w": w, "h": h,
                "sidewalk": sidewalk}

    def place_object(self, x: int, y: int, tile: str,
                     kind: str = "object") -> dict[str, Any]:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise SceneError("object is outside the scene")
        self.layers["objects"][(x, y)] = tile
        return {"x": x, "y": y, "tile": tile, "kind": kind}

    def add_fence(self, x: int, y: int, length: int, axis: str = "x",
                  kind: str = "picket", gate: bool = False,
                  tile: str = "") -> dict[str, Any]:
        if axis not in ("x", "y"):
            raise SceneError("fence axis must be x or y")
        if length <= 0:
            raise SceneError("fence length must be positive")
        w = length if axis == "x" else 1
        h = 1 if axis == "x" else length
        self.check_rect(x, y, w, h)
        self.fences.append(Fence(x=x, y=y, length=length, axis=axis,
                                 kind=kind, gate=gate, tile=tile))
        if tile:
            gate_offset = length // 2 if gate else -1
            for offset in range(length):
                if offset == gate_offset:
                    continue
                fx = x + offset if axis == "x" else x
                fy = y if axis == "x" else y + offset
                self.layers["objects"][(fx, fy)] = tile
        return {"x": x, "y": y, "length": length, "axis": axis,
                "kind": kind, "gate": gate, "tile": tile}

    def add_roof_access(self, building_id: str, x: int, y: int, z: int = 0,
                        to_z: int = 1, kind: str = "stairs") -> dict[str, Any]:
        building = self.buildings.get(building_id)
        if building is None:
            raise SceneError(f"unknown building: {building_id}")
        if not (building.x <= x < building.x + building.w and
                building.y <= y < building.y + building.h):
            raise SceneError("roof access must be inside the building footprint")
        if to_z <= z:
            raise SceneError("to_z must be above z")
        self.stairs.append(Stair(building=building_id, x=x, y=y, z=z,
                                 to_z=to_z, kind=kind))
        return {"building": building_id, "x": x, "y": y, "z": z,
                "to_z": to_z, "kind": kind}

    def add_story(self, x: int, y: int, w: int = 1, h: int = 1,
                  kind: str = "story", name: str = "") -> dict[str, Any]:
        self.check_rect(x, y, w, h)
        story_id = f"story-{len(self.stories) + 1}"
        self.stories.append(StorySite(
            id=story_id, kind=kind, name=name or kind, x=x, y=y, w=w, h=h,
        ))
        return {"story": story_id, "kind": kind, "x": x, "y": y, "w": w, "h": h}

    def remove_story(self, story_id: str) -> dict[str, Any]:
        for index, story in enumerate(self.stories):
            if story.id == story_id:
                del self.stories[index]
                return {"removed": story_id}
        raise SceneError(f"unknown story: {story_id}")

    def add_spawn(self, x: int, y: int, z: int = 0,
                  profession: str = "unemployed") -> dict[str, Any]:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise SceneError("spawn is outside the scene")
        self.spawns.append(Spawn(x=x, y=y, z=z, profession=profession))
        return {"spawn": len(self.spawns) - 1, "x": x, "y": y, "z": z}

    def remove_spawn(self, index: int) -> dict[str, Any]:
        if not (0 <= index < len(self.spawns)):
            raise SceneError("spawn index out of range")
        del self.spawns[index]
        return {"removed": index}

    def undo(self) -> dict[str, Any]:
        if not self._history:
            raise SceneError("nothing to undo")
        current = json.dumps(self.to_dict(), sort_keys=True)
        previous = self._history.pop()
        self._redo.append(current)
        restored = Scene.from_dict(json.loads(previous))
        history, redo = self._history, self._redo
        self.__dict__.update(restored.__dict__)
        self._history, self._redo = history, redo
        return {"undone": True}

    def redo(self) -> dict[str, Any]:
        if not self._redo:
            raise SceneError("nothing to redo")
        target = self._redo.pop()
        self._history.append(json.dumps(self.to_dict(), sort_keys=True))
        restored = Scene.from_dict(json.loads(target))
        history, redo = self._history, self._redo
        self.__dict__.update(restored.__dict__)
        self._history, self._redo = history, redo
        return {"redone": True}

    # --------------------------------------------------------------- persistence
    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Scene":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def query_area(self, x: int, y: int, w: int, h: int,
                   layer: str | None = None) -> dict[str, Any]:
        """Compact area query for agents: no whole-map JSON."""
        self.check_rect(x, y, w, h)
        layers = {}
        names = [layer] if layer else list(self.layers)
        for name in names:
            if name not in self.layers:
                raise SceneError(f"unknown layer: {name}")
            cells = [{"x": cx, "y": cy, "tile": tile}
                     for (cx, cy), tile in self.layers[name].items()
                     if x <= cx < x + w and y <= cy < y + h]
            if cells:
                layers[name] = cells
        buildings = [b.to_dict() for b in self.buildings.values()
                     if not (b.x + b.w <= x or b.x >= x + w or
                             b.y + b.h <= y or b.y >= y + h)]
        spawns = [s.to_dict() for s in self.spawns if x <= s.x < x + w and y <= s.y < y + h]
        stories = [s.to_dict() for s in self.stories
                   if not (s.x + s.w <= x or s.x >= x + w or
                           s.y + s.h <= y or s.y >= y + h)]
        fences = [f.to_dict() for f in self.fences
                  if x <= f.x < x + w and y <= f.y < y + h]
        return {"bbox": [x, y, w, h], "layers": layers, "buildings": buildings,
                "spawns": spawns, "stories": stories, "fences": fences}

    def stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "layers": {k: len(v) for k, v in self.layers.items()},
            "buildings": len(self.buildings),
            "floors": sum(len(b.floors) for b in self.buildings.values()),
            "furniture": sum(len(f.furniture) for b in self.buildings.values()
                             for f in b.floors.values()),
            "spawns": len(self.spawns),
            "stories": len(self.stories),
            "stairs": len(self.stairs),
            "fences": len(self.fences),
            "references": len(self.references),
        }


def parse_spawnpoints(text: str) -> list[tuple[int, int, int]]:
    positions = []
    for x, y, z in re.findall(
            r"posX\s*=\s*(-?\d+)\s*,\s*posY\s*=\s*(-?\d+)\s*,\s*posZ\s*=\s*(-?\d+)",
            text):
        positions.append((int(x), int(y), int(z)))
    return positions


def import_pz_region(map_dir: str | Path, x: int, y: int, w: int, h: int,
                     name: str | None = None, max_level: int = 0,
                     step: int = 1, clean: bool = True,
                     include_buildings: bool = True) -> Scene:
    """Import a tile rectangle from a compiled PZ map into an editable scene.

    Coordinates are absolute compiled-tile coordinates (the same coordinates as
    ``spawnpoints.lua``). The result is a local scene of ``w`` by ``h`` tiles;
    spawn points are shifted into local coordinates.
    """
    from .pzlot import classify_tile, iter_cell, read_header_full

    path = Path(map_dir)
    if w <= 0 or h <= 0:
        raise SceneError("width and height must be positive")
    scene = Scene(name=name or f"{path.name} {x},{y} {w}x{h}", width=w, height=h)
    x0, y0, x1, y1 = x, y, x + w, y + h
    furniture_candidates: list[tuple[int, int, int, str]] = []
    cell_x0, cell_y0 = x0 // 256, y0 // 256
    cell_x1, cell_y1 = (x1 - 1) // 256, (y1 - 1) // 256
    for cell_x in range(cell_x0, cell_x1 + 1):
        for cell_y in range(cell_y0, cell_y1 + 1):
            header = path / f"{cell_x}_{cell_y}.lotheader"
            if not header.exists():
                continue
            for wx, wy, z, names in iter_cell(path, cell_x, cell_y, max_level=max_level):
                if not (x0 <= wx < x1 and y0 <= wy < y1):
                    continue
                if step > 1 and (wx - x0) % step or step > 1 and (wy - y0) % step:
                    continue
                layer, tile = classify_tile(names)
                scene.layers[layer][(wx - x0, wy - y0)] = tile
                joined = " ".join(names).lower()
                kind = None
                for needle, name_kind in (
                    ("furniture_bed", "bed"), ("bed_", "bed"),
                    ("furniture_tables", "table"), ("table_", "table"),
                    ("furniture_chairs", "chair"), ("chair_", "chair"),
                    ("appliances_cooking", "kitchen"), ("fixtures_counters", "counter"),
                    ("fixtures_sinks", "sink"), ("fixtures_bathroom", "toilet"),
                    ("furniture_sofas", "sofa"), ("furniture_shelving", "shelf"),
                    ("lighting_indoor", "lamp"),
                ):
                    if needle in joined:
                        kind = name_kind
                        break
                if kind:
                    furniture_candidates.append((wx - x0, wy - y0, z, kind))
            # Rooms and buildings from the header. Room rectangles are local
            # to the 256-tile cell, so shift them into the region.
            if not include_buildings:
                continue
            try:
                _header, rooms, buildings = read_header_full(header)
            except Exception:
                continue
            for b_index, room_ids in enumerate(buildings):
                floors: dict[int, object] = {}
                min_x = min_y = 10**18
                max_x = max_y = -10**18
                for room_id in room_ids:
                    if not (0 <= room_id < len(rooms)):
                        continue
                    room_name, level, rects = rooms[room_id]
                    for rx, ry, rw, rh in rects:
                        gx, gy = cell_x * 256 + rx, cell_y * 256 + ry
                        if gx + rw <= x0 or gx >= x1 or gy + rh <= y0 or gy >= y1:
                            continue
                        lx = max(0, gx - x0)
                        ly = max(0, gy - y0)
                        lw = min(w, gx + rw - x0) - lx
                        lh = min(h, gy + rh - y0) - ly
                        if lw <= 0 or lh <= 0:
                            continue
                        floor = floors.get(level)
                        if floor is None:
                            floor = Floor(z=level)
                            floors[level] = floor
                        floor.rooms.append(Room(lx, ly, lw, lh, room_name or "room"))
                        min_x = min(min_x, lx)
                        min_y = min(min_y, ly)
                        max_x = max(max_x, lx + lw)
                        max_y = max(max_y, ly + lh)
                if floors:
                    building_id = f"cell-{cell_x}-{cell_y}-b{b_index}"
                    scene.buildings[building_id] = Building(
                        id=building_id, name=f"{path.name} {building_id}",
                        x=min_x, y=min_y, w=max_x - min_x, h=max_y - min_y,
                        floors=floors,
                    )
    if furniture_candidates:
        room_owner: dict[tuple[int, int, int], tuple[str, int]] = {}
        for building in scene.buildings.values():
            for z, floor in building.floors.items():
                for room in floor.rooms:
                    for ry in range(room.y, room.y + room.h):
                        for rx in range(room.x, room.x + room.w):
                            room_owner[(rx, ry, z)] = (building.id, z)
        for fx, fy, fz, kind in furniture_candidates:
            owner = room_owner.get((fx, fy, fz))
            if owner is None:
                continue
            building = scene.buildings.get(owner[0])
            floor = building.floors.get(owner[1]) if building else None
            if floor is not None:
                floor.furniture.append(Furniture(kind=kind, x=fx, y=fy, z=fz))

    if clean and scene.buildings:
        scene.clean_interiors()

    spawn_file = path / "spawnpoints.lua"
    if spawn_file.exists():
        for sx, sy, sz in parse_spawnpoints(spawn_file.read_text(errors="ignore")):
            if x0 <= sx < x1 and y0 <= sy < y1:
                scene.spawns.append(Spawn(x=sx - x0, y=sy - y0, z=sz))
    return scene


def import_pz_map(map_dir: str | Path, name: str | None = None) -> Scene:
    """Create an editable overlay from a compiled PZ map folder.

    Cell files are named by absolute 256-tile coordinates; their maximum gives
    the scene bounds. Spawn points and their Lua positions are imported. The
    compiled terrain itself is not decoded yet.
    """
    path = Path(map_dir)
    cells = []
    for header in path.glob("*.lotheader"):
        parts = header.stem.split("_")
        try:
            cells.append((int(parts[-2]), int(parts[-1])))
        except (ValueError, IndexError):
            continue
    if not cells:
        raise SceneError(f"no .lotheader files in {path}")
    width = (max(x for x, _ in cells) + 1) * 256
    height = (max(y for _, y in cells) + 1) * 256
    title = path.name
    info = path / "map.info"
    if info.exists():
        for line in info.read_text(errors="ignore").splitlines():
            if line.startswith("title="):
                title = line.split("=", 1)[1].strip()
                break
    scene = Scene(name=name or title, width=width, height=height)
    spawn_file = path / "spawnpoints.lua"
    if spawn_file.exists():
        for x, y, z in parse_spawnpoints(spawn_file.read_text(errors="ignore")):
            if 0 <= x < width and 0 <= y < height:
                scene.spawns.append(Spawn(x=x, y=y, z=z))
    return scene


def import_knoxmap(pzw_path: str | Path, spawnpoints_path: str | Path | None = None,
                   name: str | None = None) -> Scene:
    """Create an editable overlay for a KnoxMap .pzw project.

    World dimensions are in 300-tile cells in the PZW. The compiled map is
    larger than that in places, but the project dimensions are the best available
    origin for an overlay.
    """
    import xml.etree.ElementTree as ET
    root = ET.parse(pzw_path).getroot()
    width = int(root.attrib.get("width", "1")) * 300
    height = int(root.attrib.get("height", "1")) * 300
    scene = Scene(name=name or Path(pzw_path).stem, width=width, height=height)
    if spawnpoints_path and Path(spawnpoints_path).exists():
        for x, y, z in parse_spawnpoints(Path(spawnpoints_path).read_text(encoding="utf-8")):
            if 0 <= x < width and 0 <= y < height:
                scene.spawns.append(Spawn(x=x, y=y, z=z))
    return scene
