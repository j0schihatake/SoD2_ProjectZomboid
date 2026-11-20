"""PNG preview for a :class:`pzmapstudio.scene.Scene`."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .scene import Scene

TERRAIN_COLORS = {
    "grass": (104, 142, 72),
    "forest": (46, 94, 54),
    "farm": (162, 154, 86),
    "water": (58, 112, 170),
    "sand": (194, 176, 112),
}
ROAD_COLORS = {
    "asphalt": (54, 54, 58),
    "gravel": (126, 118, 96),
    "dirt": (112, 88, 58),
    "rail": (80, 70, 66),
    "sidewalk": (150, 148, 138),
}
FURNITURE_COLORS = {
    "bed": (186, 132, 148),
    "table": (145, 104, 64),
    "chair": (120, 88, 60),
    "kitchen": (170, 170, 150),
    "lamp": (214, 192, 92),
}
SPAWN_COLOR = (230, 54, 54)
BUILDING_FILL = (214, 150, 110)
BUILDING_EDGE = (70, 42, 34)
WALL_COLOR = (88, 58, 42)


def render(scene: Scene, path: str | Path, floor: int = 0,
           max_pixels: int = 1800) -> Path:
    """Render a top-down preview.

    Large scenes are scaled down to ``max_pixels`` on the longest side. The
    image is deliberately schematic: it is a planning/debug view, not a
    replacement for the in-game renderer.
    """
    largest = max(scene.width, scene.height, 1)
    scale = min(4.0, max_pixels / largest)
    width = max(1, int(scene.width * scale))
    height = max(1, int(scene.height * scale))
    image = Image.new("RGB", (width, height), (78, 106, 62))
    draw = ImageDraw.Draw(image)

    def box(x: int, y: int, w: int = 1, h: int = 1):
        return (
            int(x * scale), int(y * scale),
            max(int((x + w) * scale), int(x * scale) + 1),
            max(int((y + h) * scale), int(y * scale) + 1),
        )

    # terrain
    for (x, y), tile in scene.layers["terrain"].items():
        draw.rectangle(box(x, y), fill=TERRAIN_COLORS.get(tile, (100, 120, 80)))
    # water above roads/terrain
    for (x, y), tile in scene.layers["water"].items():
        draw.rectangle(box(x, y), fill=TERRAIN_COLORS["water"])
    # roads
    for (x, y), tile in scene.layers["roads"].items():
        draw.rectangle(box(x, y), fill=ROAD_COLORS.get(tile, (72, 72, 72)))
    # sidewalks
    for (x, y), _tile in scene.layers.get("sidewalks", {}).items():
        draw.rectangle(box(x, y), fill=ROAD_COLORS["sidewalk"])
    # floor tiles
    for (x, y), tile in scene.layers["floors"].items():
        draw.rectangle(box(x, y), fill=(170, 150, 118))
    # fences
    for fence in scene.fences:
        if fence.axis == "x":
            draw.line([(int(fence.x * scale), int((fence.y + 0.5) * scale)),
                       (int((fence.x + fence.length) * scale), int((fence.y + 0.5) * scale))],
                      fill=(116, 78, 46), width=max(1, int(scale)))
        else:
            draw.line([(int((fence.x + 0.5) * scale), int(fence.y * scale)),
                       (int((fence.x + 0.5) * scale), int((fence.y + fence.length) * scale))],
                      fill=(116, 78, 46), width=max(1, int(scale)))
    # buildings and furniture for the selected floor
    for building in scene.buildings.values():
        draw.rectangle(box(building.x, building.y, building.w, building.h),
                       fill=BUILDING_FILL, outline=BUILDING_EDGE, width=max(1, int(scale)))
        if building.outline:
            points = [(int(x * scale), int(y * scale)) for x, y in building.outline]
            draw.line(points + [points[0]], fill=(70, 42, 34), width=max(1, int(2 * scale)))
        floor_data = building.floors.get(floor)
        if not floor_data:
            continue
        for room in floor_data.rooms:
            draw.rectangle(box(room.x, room.y, room.w, room.h),
                           outline=(92, 70, 52), width=max(1, int(scale)))
        for item in floor_data.furniture:
            draw.rectangle(box(item.x, item.y),
                           fill=FURNITURE_COLORS.get(item.kind, (160, 130, 90)))
    # walls
    for (x, y), tile in scene.layers["walls"].items():
        draw.rectangle(box(x, y), fill=WALL_COLOR)
    # roof access
    for stair in scene.stairs:
        draw.rectangle(box(stair.x, stair.y), fill=(80, 170, 220),
                       outline=(235, 245, 255))
    # story sites
    for story in scene.stories:
        draw.rectangle(box(story.x, story.y, story.w, story.h),
                       outline=(230, 160, 50), width=max(1, int(2 * scale)))
        draw.text((int(story.x * scale) + 2, int(story.y * scale) + 2),
                  story.kind, fill=(255, 220, 150))
    # spawn markers
    radius = max(2, int(3 * scale))
    for spawn in scene.spawns:
        cx = int((spawn.x + 0.5) * scale)
        cy = int((spawn.y + 0.5) * scale)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                     fill=SPAWN_COLOR, outline=(255, 230, 210))
    # title/stats
    draw.rectangle((4, 4, min(width - 4, 480), 26), fill=(20, 24, 20))
    draw.text((10, 8), f"{scene.name}  {scene.width}x{scene.height}  floor {floor}",
              fill=(235, 235, 225))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path
