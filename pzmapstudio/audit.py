"""Practical placement and map sanity checks for a scene."""
from __future__ import annotations

from .scene import Scene


def audit_scene(scene: Scene) -> dict:
    issues: list[dict] = []
    warnings: list[dict] = []

    def issue(kind: str, message: str, **where):
        issues.append({"kind": kind, "message": message, **where})

    for index, spawn in enumerate(scene.spawns):
        if not (0 <= spawn.x < scene.width and 0 <= spawn.y < scene.height):
            issue("spawn-outside", "spawn is outside the map", index=index)

    for building in scene.buildings.values():
        if building.w <= 0 or building.h <= 0:
            issue("building-size", "building has no area", building=building.id)
        outdoor = 0
        for yy in range(building.y, building.y + building.h):
            for xx in range(building.x, building.x + building.w):
                if any((xx, yy) in scene.layers[layer]
                       for layer in ("terrain", "roads", "sidewalks", "water")):
                    outdoor += 1
        if outdoor:
            issue("outdoor-ground-inside", "outdoor ground inside building footprint",
                  building=building.id, tiles=outdoor)
        for z, floor in building.floors.items():
            for room in floor.rooms:
                if not (building.x <= room.x < building.x + building.w and
                        building.y <= room.y < building.y + building.h):
                    issue("room-outside", "room leaves the building", building=building.id,
                          z=z)
            for item in floor.furniture:
                if not (building.x <= item.x < building.x + building.w and
                        building.y <= item.y < building.y + building.h):
                    issue("furniture-outside", "furniture leaves the building",
                          building=building.id, z=z, kind=item.kind)
                if (item.x, item.y) in scene.layers["walls"]:
                    issue("furniture-in-wall", "furniture is on a wall",
                          building=building.id, z=z, kind=item.kind)

    for stair in scene.stairs:
        building = scene.buildings.get(stair.building)
        if building is None:
            issue("stair-orphan", "stair references a missing building",
                  building=stair.building)
            continue
        if not (building.x <= stair.x < building.x + building.w and
                building.y <= stair.y < building.y + building.h):
            issue("stair-outside", "stair is outside its building", building=stair.building)
        if stair.to_z <= stair.z:
            issue("stair-direction", "roof access does not go up", building=stair.building)
        if stair.to_z not in building.floors and building.floors:
            warnings.append({"kind": "stair-floor-missing",
                             "message": "roof target has no imported floor",
                             "building": stair.building, "to_z": stair.to_z})

    for key in scene.layers["roads"]:
        if key in scene.layers["terrain"] or key in scene.layers["water"]:
            issue("ground-under-road", "grass/water under a road tile", x=key[0], y=key[1])

    for key in scene.layers["sidewalks"]:
        if key in scene.layers["terrain"] or key in scene.layers["water"]:
            issue("ground-under-sidewalk", "grass/water under a sidewalk tile",
                  x=key[0], y=key[1])

    for fence in scene.fences:
        if fence.x < 0 or fence.y < 0:
            issue("fence-outside", "fence starts outside the map")
        if fence.axis == "x" and fence.x + fence.length > scene.width:
            issue("fence-outside", "fence leaves the map")
        if fence.axis == "y" and fence.y + fence.length > scene.height:
            issue("fence-outside", "fence leaves the map")

    for story in scene.stories:
        if not (0 <= story.x < scene.width and 0 <= story.y < scene.height):
            issue("story-outside", "story site is outside the map", story=story.id)

    stats = scene.stats()
    return {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "stats": stats,
    }
