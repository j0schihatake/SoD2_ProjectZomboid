"""Command line entry point."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .address import (AddressError, download_photo, footprint_dimensions, geocode,
                      google_maps_url, wikimedia_photos, wikimedia_search)
from .audit import audit_scene
from .catalog import build_catalog, Catalog
from .export import (apply_scene_objects, apply_scene_roads, export_bundle,
                     export_pz_region, export_tmx)
from .worlded import export_scene_cell as export_worlded_cell
from .worlded import export_scene_map as export_worlded_map
from .guide import format_help
from .render import render
from .layout import audit_layout
from .lighten import lighten_map
from .save_audit import audit_map_root, audit_map_save
from .shift import shift_map
from .trim import trim_map
from .validate import validate_map
from .space import extents, find_space
from .scene import Scene, SceneError, import_knoxmap, import_pz_map, import_pz_region


def _rect(value: str) -> tuple[int, int, int, int]:
    parts = [int(part) for part in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("rect must be x,y,w,h")
    return tuple(parts)  # type: ignore[return-value]


def _load(path: str) -> Scene:
    return Scene.load(path)


def _save(scene: Scene, path: str) -> None:
    scene.save(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pzmapstudio")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new")
    new.add_argument("--name", default="Untitled")
    new.add_argument("--width", type=int, default=512)
    new.add_argument("--height", type=int, default=512)
    new.add_argument("--out", required=True)

    paint = sub.add_parser("paint")
    paint.add_argument("--scene", required=True)
    paint.add_argument("--layer", default="terrain")
    paint.add_argument("--rect", type=_rect, required=True)
    paint.add_argument("--tile", required=True)

    erase = sub.add_parser("erase")
    erase.add_argument("--scene", required=True)
    erase.add_argument("--layer", default="terrain")
    erase.add_argument("--rect", type=_rect, required=True)

    worlded = sub.add_parser("export-worlded-cell")
    worlded.add_argument("--scene", required=True)
    worlded.add_argument("--out", required=True)
    worlded.add_argument("--cell-x", type=int, default=0)
    worlded.add_argument("--cell-y", type=int, default=0)
    worlded.add_argument("--origin-x", type=int, default=0)
    worlded.add_argument("--origin-y", type=int, default=0)

    worlded_map = sub.add_parser("export-worlded-map")
    worlded_map.add_argument("--scene", required=True)
    worlded_map.add_argument("--out", required=True)
    worlded_map.add_argument("--cell-x", type=int, default=0)
    worlded_map.add_argument("--cell-y", type=int, default=0)
    worlded_map.add_argument("--origin-x", type=int, default=0)
    worlded_map.add_argument("--origin-y", type=int, default=0)

    footprint = sub.add_parser("build-footprint")
    footprint.add_argument("--scene", required=True)
    footprint.add_argument("--points", required=True,
                           help="x,y;x,y;... absolute tile coordinates")
    footprint.add_argument("--floors", type=int, default=1)
    footprint.add_argument("--rooms", type=int, default=4)
    footprint.add_argument("--name", default="")

    typed = sub.add_parser("build-typed")
    typed.add_argument("--scene", required=True)
    typed.add_argument("--kind", required=True,
                       choices=["house", "church", "courthouse", "school", "clinic",
                                "barn", "warehouse", "shop", "mill", "fair_hall"])
    typed.add_argument("--x", type=int, required=True)
    typed.add_argument("--y", type=int, required=True)
    typed.add_argument("--w", type=int, required=True)
    typed.add_argument("--h", type=int, required=True)
    typed.add_argument("--floors", type=int, default=1)
    typed.add_argument("--no-furnish", action="store_true")
    typed.add_argument("--name", default="")

    house = sub.add_parser("build-house")
    house.add_argument("--scene", required=True)
    house.add_argument("--x", type=int, required=True)
    house.add_argument("--y", type=int, required=True)
    house.add_argument("--w", type=int, required=True)
    house.add_argument("--h", type=int, required=True)
    house.add_argument("--floors", type=int, default=1)
    house.add_argument("--rooms", type=int, default=4)
    house.add_argument("--no-furnish", action="store_true")
    house.add_argument("--name", default="")

    floor = sub.add_parser("add-floor")
    floor.add_argument("--scene", required=True)
    floor.add_argument("--building", required=True)
    floor.add_argument("--z", type=int, required=True)
    floor.add_argument("--rooms", type=int, default=4)

    furniture = sub.add_parser("place-furniture")
    furniture.add_argument("--scene", required=True)
    furniture.add_argument("--building", required=True)
    furniture.add_argument("--x", type=int, required=True)
    furniture.add_argument("--y", type=int, required=True)
    furniture.add_argument("--z", type=int, default=0)
    furniture.add_argument("--kind", default="chair")

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--scene", required=True)
    inspect.add_argument("--bbox", required=True, help="x,y,w,h")
    inspect.add_argument("--layer", default=None)

    audit = sub.add_parser("audit")
    audit.add_argument("--scene", required=True)

    floorplan = sub.add_parser("lookup-floorplan")
    floorplan.add_argument("--address", required=True)
    floorplan.add_argument("--scene", default="")
    floorplan.add_argument("--building", default="")
    floorplan.add_argument("--out-dir", default="references")
    floorplan.add_argument("--limit", type=int, default=5)

    photo = sub.add_parser("lookup-photo")
    photo.add_argument("--address", required=True)
    photo.add_argument("--scene", default="")
    photo.add_argument("--building", default="")
    photo.add_argument("--out-dir", default="references")
    photo.add_argument("--limit", type=int, default=5)
    photo.add_argument("--radius", type=int, default=500)

    lookup = sub.add_parser("lookup-address")
    lookup.add_argument("--address", required=True)
    lookup.add_argument("--scene", default="")
    lookup.add_argument("--building", default="")
    lookup.add_argument("--photo", default="")
    lookup.add_argument("--improvise", action="store_true")
    lookup.add_argument("--x", type=int, default=0)
    lookup.add_argument("--y", type=int, default=0)
    lookup.add_argument("--meters-per-tile", type=float, default=2.0)
    lookup.add_argument("--rooms", type=int, default=4)

    ref = sub.add_parser("add-reference")
    ref.add_argument("--scene", required=True)
    ref.add_argument("--title", required=True)
    ref.add_argument("--url", default="")
    ref.add_argument("--path", default="")
    ref.add_argument("--building", default="")
    ref.add_argument("--lat", type=float, default=None)
    ref.add_argument("--lon", type=float, default=None)
    ref.add_argument("--notes", default="")
    ref.add_argument("--kind", choices=["photo", "floorplan", "map", "other"],
                     default="photo")

    clean = sub.add_parser("clean-interiors")
    clean.add_argument("--scene", required=True)

    clean_roads = sub.add_parser("clean-roads")
    clean_roads.add_argument("--scene", required=True)

    auto_roof = sub.add_parser("auto-roof-access")
    auto_roof.add_argument("--scene", required=True)
    auto_roof.add_argument("--min-area", type=int, default=120)
    auto_roof.add_argument("--kind", default="ladder")

    art = sub.add_parser("art-pass")
    art.add_argument("--scene", required=True)
    art.add_argument("--min-roof-area", type=int, default=120)
    art.add_argument("--roof-kind", default="ladder")

    road = sub.add_parser("add-road")
    road.add_argument("--scene", required=True)
    road.add_argument("--x", type=int, required=True)
    road.add_argument("--y", type=int, required=True)
    road.add_argument("--w", type=int, required=True)
    road.add_argument("--h", type=int, required=True)
    road.add_argument("--material", default="asphalt")
    road.add_argument("--no-sidewalk", action="store_true")

    obj = sub.add_parser("place-object")
    obj.add_argument("--scene", required=True)
    obj.add_argument("--x", type=int, required=True)
    obj.add_argument("--y", type=int, required=True)
    obj.add_argument("--tile", required=True)
    obj.add_argument("--kind", default="object")

    fence = sub.add_parser("add-fence")
    fence.add_argument("--scene", required=True)
    fence.add_argument("--x", type=int, required=True)
    fence.add_argument("--y", type=int, required=True)
    fence.add_argument("--length", type=int, required=True)
    fence.add_argument("--axis", choices=["x", "y"], default="x")
    fence.add_argument("--kind", default="picket")
    fence.add_argument("--gate", action="store_true")
    fence.add_argument("--tile", default="",
                       help="PZ tile name for the fence line")

    roof = sub.add_parser("add-roof-access")
    roof.add_argument("--scene", required=True)
    roof.add_argument("--building", required=True)
    roof.add_argument("--x", type=int, required=True)
    roof.add_argument("--y", type=int, required=True)
    roof.add_argument("--z", type=int, default=0)
    roof.add_argument("--to-z", type=int, default=1)
    roof.add_argument("--kind", default="stairs")

    story = sub.add_parser("add-story")
    story.add_argument("--scene", required=True)
    story.add_argument("--x", type=int, required=True)
    story.add_argument("--y", type=int, required=True)
    story.add_argument("--w", type=int, default=1)
    story.add_argument("--h", type=int, default=1)
    story.add_argument("--kind", default="story")
    story.add_argument("--name", default="")

    spawn = sub.add_parser("add-spawn")
    spawn.add_argument("--scene", required=True)
    spawn.add_argument("--x", type=int, required=True)
    spawn.add_argument("--y", type=int, required=True)
    spawn.add_argument("--z", type=int, default=0)
    spawn.add_argument("--profession", default="unemployed")

    batch = sub.add_parser("apply-batch")
    batch.add_argument("--scene", required=True)
    batch.add_argument("--commands", required=True, help="JSON array of commands")

    undo = sub.add_parser("undo")
    undo.add_argument("--scene", required=True)
    redo = sub.add_parser("redo")
    redo.add_argument("--scene", required=True)

    preview = sub.add_parser("render")
    preview.add_argument("--scene", required=True)
    preview.add_argument("--out", required=True)
    preview.add_argument("--floor", type=int, default=0)

    apply_objects = sub.add_parser("apply-object-pass")
    apply_objects.add_argument("--source-map", required=True)
    apply_objects.add_argument("--scene", required=True)
    apply_objects.add_argument("--out", required=True)
    apply_objects.add_argument("--origin-x", type=int, required=True)
    apply_objects.add_argument("--origin-y", type=int, required=True)
    apply_objects.add_argument("--layer", default="objects")

    apply_roads = sub.add_parser("apply-road-pass")
    apply_roads.add_argument("--source-map", required=True)
    apply_roads.add_argument("--scene", required=True)
    apply_roads.add_argument("--out", required=True)
    apply_roads.add_argument("--origin-x", type=int, required=True)
    apply_roads.add_argument("--origin-y", type=int, required=True)

    export_pz = sub.add_parser("export-pz-region")
    export_pz.add_argument("--scene", required=True)
    export_pz.add_argument("--out", required=True)
    export_pz.add_argument("--cell-x", type=int, default=0)
    export_pz.add_argument("--cell-y", type=int, default=0)

    export = sub.add_parser("export")
    export.add_argument("--scene", required=True)
    export.add_argument("--out", required=True)
    export.add_argument("--tmx", action="store_true")

    import_pz = sub.add_parser("import-knoxmap")
    import_pz.add_argument("--pzw", required=True)
    import_pz.add_argument("--spawnpoints", default=None)
    import_pz.add_argument("--out", required=True)

    import_map = sub.add_parser("import-pz-map")
    import_map.add_argument("--map", required=True)
    import_map.add_argument("--out", required=True)
    import_map.add_argument("--name", default=None)

    import_region = sub.add_parser("import-pz-region")
    import_region.add_argument("--map", required=True)
    import_region.add_argument("--x", type=int, required=True)
    import_region.add_argument("--y", type=int, required=True)
    import_region.add_argument("--width", type=int, required=True)
    import_region.add_argument("--height", type=int, required=True)
    import_region.add_argument("--out", required=True)
    import_region.add_argument("--name", default=None)
    import_region.add_argument("--max-level", type=int, default=0)
    import_region.add_argument("--step", type=int, default=1)
    import_region.add_argument("--keep-outdoor", action="store_true")

    lighten = sub.add_parser("lighten-map")
    lighten.add_argument("--source", required=True)
    lighten.add_argument("--out", required=True)

    trim = sub.add_parser("trim-map")
    trim.add_argument("--source", required=True)
    trim.add_argument("--out", required=True)
    trim.add_argument("--cells", required=True, help="x0,y0,x1,y1 in 256-tile cells")

    shift = sub.add_parser("shift-map")
    shift.add_argument("--source", required=True)
    shift.add_argument("--out", required=True)
    shift.add_argument("--dx-cells", type=int, required=True,
                       help="256-tile cells, not 300-tile world cells")
    shift.add_argument("--dy-cells", type=int, required=True)
    shift.add_argument("--shift-objects", action="store_true")

    layout = sub.add_parser("layout-audit")
    layout.add_argument("--map-root", required=True)

    space_parser = sub.add_parser("find-space")
    space_parser.add_argument("--map-root", required=True,
                              help="folder containing map folders")
    space_parser.add_argument("--width", type=int, required=True)
    space_parser.add_argument("--height", type=int, required=True)
    space_parser.add_argument("--limit", type=int, default=400)

    validate = sub.add_parser("validate-map")
    validate.add_argument("--map", required=True)

    save_audit = sub.add_parser("map-save-audit")
    save_group = save_audit.add_mutually_exclusive_group(required=True)
    save_group.add_argument("--map", default=None)
    save_group.add_argument("--map-root", default=None)

    catalog = sub.add_parser("build-catalog")
    catalog.add_argument("--pz-root", required=True,
                         help="ProjectZomboid/projectzomboid directory")
    catalog.add_argument("--out", required=True)

    search = sub.add_parser("search-catalog")
    search.add_argument("--catalog", required=True)
    search.add_argument("--kind", choices=["all", "tiles", "items", "stories"],
                        default="all")
    search.add_argument("--query", default="")
    search.add_argument("--limit", type=int, default=50)

    help_parser = sub.add_parser("help", help="agent-readable capability guide")
    help_parser.add_argument("--json", action="store_true",
                             help="machine-readable command catalog")

    api = sub.add_parser("serve")
    api.add_argument("--scene", required=True)
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8765)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "help":
            print(format_help(json_mode=args.json))
        elif args.command == "new":
            Scene(name=args.name, width=args.width, height=args.height).save(args.out)
            print(args.out)
        elif args.command == "paint":
            scene = _load(args.scene)
            print(scene.apply({"op": "paint", "layer": args.layer, "x": args.rect[0],
                               "y": args.rect[1], "w": args.rect[2], "h": args.rect[3],
                               "tile": args.tile}))
            _save(scene, args.scene)
        elif args.command == "erase":
            scene = _load(args.scene)
            print(scene.apply({"op": "erase", "layer": args.layer, "x": args.rect[0],
                               "y": args.rect[1], "w": args.rect[2], "h": args.rect[3]}))
            _save(scene, args.scene)
        elif args.command == "export-worlded-cell":
            scene = _load(args.scene)
            print(export_worlded_cell(scene, args.out, args.cell_x, args.cell_y,
                                      args.origin_x, args.origin_y))
        elif args.command == "export-worlded-map":
            scene = _load(args.scene)
            print(export_worlded_map(scene, args.out, args.cell_x, args.cell_y,
                                     args.origin_x, args.origin_y))
        elif args.command == "build-footprint":
            scene = _load(args.scene)
            points = []
            for chunk in args.points.split(";"):
                x, y = chunk.split(",")
                points.append((int(x), int(y)))
            print(scene.apply({"op": "build_footprint", "points": points,
                               "floors": args.floors, "rooms": args.rooms,
                               "name": args.name}))
            _save(scene, args.scene)
        elif args.command == "build-typed":
            scene = _load(args.scene)
            print(scene.apply({
                "op": "build_typed", "kind": args.kind,
                "x": args.x, "y": args.y, "w": args.w, "h": args.h,
                "floors": args.floors, "furnish": not args.no_furnish,
                "name": args.name,
            }))
            _save(scene, args.scene)
        elif args.command == "build-house":
            scene = _load(args.scene)
            print(scene.apply({
                "op": "build_house", "x": args.x, "y": args.y, "w": args.w,
                "h": args.h, "floors": args.floors, "rooms": args.rooms,
                "furnish": not args.no_furnish, "name": args.name,
            }))
            _save(scene, args.scene)
        elif args.command == "add-floor":
            scene = _load(args.scene)
            print(scene.apply({"op": "add_floor", "building": args.building,
                               "z": args.z, "rooms": args.rooms}))
            _save(scene, args.scene)
        elif args.command == "place-furniture":
            scene = _load(args.scene)
            print(scene.apply({"op": "place_furniture", "building": args.building,
                               "x": args.x, "y": args.y, "z": args.z,
                               "kind": args.kind}))
            _save(scene, args.scene)
        elif args.command == "inspect":
            scene = _load(args.scene)
            x, y, w, h = (int(part) for part in args.bbox.split(","))
            print(json.dumps(scene.query_area(x, y, w, h, args.layer),
                             indent=2, ensure_ascii=False))
        elif args.command == "audit":
            scene = _load(args.scene)
            print(json.dumps(audit_scene(scene), indent=2, ensure_ascii=False))
        elif args.command == "lookup-floorplan":
            try:
                result = geocode(args.address)
                photos = wikimedia_search(f"{args.address} floor plan", limit=args.limit)
            except AddressError as error:
                print(json.dumps({"error": str(error)}, indent=2, ensure_ascii=False))
                return 2
            print(json.dumps({"address": result.to_dict(), "floorplans": photos},
                             indent=2, ensure_ascii=False))
            if args.scene:
                scene = _load(args.scene)
                for index, item in enumerate(photos):
                    suffix = Path(item["url"]).suffix or ".jpg"
                    path = Path(args.out_dir) / f"floorplan-{index + 1}{suffix}"
                    try:
                        download_photo(item["url"], path)
                    except AddressError as error:
                        print(error)
                        continue
                    scene.apply({"op": "add_reference", "title": item["title"],
                                 "url": item["descriptionurl"], "path": str(path),
                                 "building": args.building, "lat": result.lat,
                                 "lon": result.lon, "notes": item.get("license", ""),
                                 "kind": "floorplan"})
                _save(scene, args.scene)
        elif args.command == "lookup-photo":
            try:
                result = geocode(args.address)
                photos = wikimedia_photos(result.lat, result.lon,
                                          radius=args.radius, limit=args.limit)
            except AddressError as error:
                print(json.dumps({"error": str(error)}, indent=2, ensure_ascii=False))
                return 2
            print(json.dumps({"address": result.to_dict(), "photos": photos},
                             indent=2, ensure_ascii=False))
            if args.scene:
                scene = _load(args.scene)
                for index, item in enumerate(photos):
                    suffix = Path(item["url"]).suffix or ".jpg"
                    path = Path(args.out_dir) / f"photo-{index + 1}{suffix}"
                    try:
                        download_photo(item["url"], path)
                    except AddressError as error:
                        print(error)
                        continue
                    scene.apply({"op": "add_reference", "title": item["title"],
                                 "url": item["descriptionurl"], "path": str(path),
                                 "building": args.building, "lat": result.lat,
                                 "lon": result.lon, "notes": item.get("license", "")})
                _save(scene, args.scene)
        elif args.command == "lookup-address":
            try:
                result = geocode(args.address)
            except AddressError as error:
                print(json.dumps({"error": str(error), "google_url": google_maps_url(args.address)},
                                 indent=2, ensure_ascii=False))
                return 2
            payload = result.to_dict()
            payload["google_url"] = google_maps_url(args.address)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            if args.scene:
                scene = _load(args.scene)
                building_id = args.building
                if args.improvise:
                    dims = footprint_dimensions(result, args.meters_per_tile)
                    w = min(200, dims["width_tiles"])
                    h = min(200, dims["height_tiles"])
                    built = scene.apply({"op": "build_house", "x": args.x, "y": args.y,
                                         "w": w, "h": h, "floors": dims["floors"],
                                         "rooms": args.rooms, "name": args.address})
                    building_id = built["building"]
                scene.apply({"op": "add_reference", "title": args.address,
                             "url": payload["google_url"], "path": args.photo,
                             "building": building_id,
                             "lat": result.lat, "lon": result.lon,
                             "notes": result.display_name})
                _save(scene, args.scene)
        elif args.command == "add-reference":
            scene = _load(args.scene)
            print(scene.apply({"op": "add_reference", "title": args.title,
                               "url": args.url, "path": args.path,
                               "building": args.building, "lat": args.lat,
                               "lon": args.lon, "notes": args.notes,
                               "kind": args.kind}))
            _save(scene, args.scene)
        elif args.command == "clean-interiors":
            scene = _load(args.scene)
            print(scene.apply({"op": "clean_interiors"}))
            _save(scene, args.scene)
        elif args.command == "clean-roads":
            scene = _load(args.scene)
            print(scene.apply({"op": "clean_roads"}))
            _save(scene, args.scene)
        elif args.command == "auto-roof-access":
            scene = _load(args.scene)
            print(scene.apply({"op": "auto_roof_access", "min_area": args.min_area,
                               "kind": args.kind}))
            _save(scene, args.scene)
        elif args.command == "art-pass":
            scene = _load(args.scene)
            print(scene.apply({"op": "art_pass", "min_roof_area": args.min_roof_area,
                               "roof_kind": args.roof_kind}))
            _save(scene, args.scene)
        elif args.command == "add-road":
            scene = _load(args.scene)
            print(scene.apply({"op": "add_road", "x": args.x, "y": args.y,
                               "w": args.w, "h": args.h, "material": args.material,
                               "sidewalk": not args.no_sidewalk}))
            _save(scene, args.scene)
        elif args.command == "place-object":
            scene = _load(args.scene)
            print(scene.apply({"op": "place_object", "x": args.x, "y": args.y,
                               "tile": args.tile, "kind": args.kind}))
            _save(scene, args.scene)
        elif args.command == "add-fence":
            scene = _load(args.scene)
            print(scene.apply({"op": "add_fence", "x": args.x, "y": args.y,
                               "length": args.length, "axis": args.axis,
                               "kind": args.kind, "gate": args.gate}))
            _save(scene, args.scene)
        elif args.command == "add-roof-access":
            scene = _load(args.scene)
            print(scene.apply({"op": "add_roof_access", "building": args.building,
                               "x": args.x, "y": args.y, "z": args.z,
                               "to_z": args.to_z, "kind": args.kind}))
            _save(scene, args.scene)
        elif args.command == "add-story":
            scene = _load(args.scene)
            print(scene.apply({"op": "add_story", "x": args.x, "y": args.y,
                               "w": args.w, "h": args.h, "kind": args.kind,
                               "name": args.name}))
            _save(scene, args.scene)
        elif args.command == "add-spawn":
            scene = _load(args.scene)
            print(scene.apply({"op": "add_spawn", "x": args.x, "y": args.y,
                               "z": args.z, "profession": args.profession}))
            _save(scene, args.scene)
        elif args.command == "apply-batch":
            scene = _load(args.scene)
            commands = json.loads(Path(args.commands).read_text(encoding="utf-8"))
            print(scene.apply_batch(commands))
            _save(scene, args.scene)
        elif args.command in ("undo", "redo"):
            scene = _load(args.scene)
            print(scene.apply({"op": args.command}))
            _save(scene, args.scene)
        elif args.command == "render":
            scene = _load(args.scene)
            print(render(scene, args.out, floor=args.floor))
        elif args.command == "apply-object-pass":
            scene = _load(args.scene)
            print(apply_scene_objects(args.source_map, scene, args.out,
                                      args.origin_x, args.origin_y, args.layer))
        elif args.command == "apply-road-pass":
            scene = _load(args.scene)
            print(apply_scene_roads(args.source_map, scene, args.out,
                                    args.origin_x, args.origin_y))
        elif args.command == "export-pz-region":
            scene = _load(args.scene)
            print(export_pz_region(scene, args.out, args.cell_x, args.cell_y))
        elif args.command == "export":
            scene = _load(args.scene)
            print(export_bundle(scene, args.out))
            if args.tmx:
                print(export_tmx(scene, Path(args.out) / "scene.tmx"))
        elif args.command == "import-knoxmap":
            scene = import_knoxmap(args.pzw, args.spawnpoints)
            scene.save(args.out)
            print(json.dumps(scene.stats(), indent=2))
        elif args.command == "import-pz-map":
            scene = import_pz_map(args.map, args.name)
            scene.save(args.out)
            print(json.dumps(scene.stats(), indent=2))
        elif args.command == "import-pz-region":
            scene = import_pz_region(args.map, args.x, args.y, args.width,
                                     args.height, args.name, args.max_level,
                                     args.step, clean=not args.keep_outdoor)
            scene.save(args.out)
            print(json.dumps(scene.stats(), indent=2))
        elif args.command == "lighten-map":
            print(lighten_map(args.source, args.out))
        elif args.command == "trim-map":
            x0, y0, x1, y1 = (int(v) for v in args.cells.split(","))
            print(trim_map(args.source, args.out, x0, y0, x1, y1))
        elif args.command == "shift-map":
            print(shift_map(args.source, args.out, args.dx_cells, args.dy_cells,
                            args.shift_objects))
        elif args.command == "layout-audit":
            print(json.dumps(audit_layout(args.map_root), indent=2, ensure_ascii=False))
        elif args.command == "find-space":
            boxes = extents([p for p in Path(args.map_root).iterdir() if p.is_dir()])
            print(json.dumps({"occupied": boxes,
                              "free": find_space(args.width, args.height, boxes,
                                                 args.limit)},
                             indent=2))
        elif args.command == "validate-map":
            print(json.dumps(validate_map(args.map), indent=2, ensure_ascii=False))
        elif args.command == "map-save-audit":
            report = (audit_map_root(args.map_root) if args.map_root
                      else audit_map_save(args.map))
            print(json.dumps(report, indent=2, ensure_ascii=False))
        elif args.command == "build-catalog":
            catalog = build_catalog(args.pz_root)
            catalog.save(args.out)
            print(json.dumps({"tiles": len(set(catalog.tiles)),
                              "items": len(set(catalog.items)),
                              "stories": len(catalog.stories)}, indent=2))
        elif args.command == "search-catalog":
            catalog = Catalog.load(args.catalog)
            print(json.dumps(catalog.search(args.kind, args.query, args.limit),
                             indent=2, ensure_ascii=False))
        elif args.command == "serve":
            from .api import serve
            serve(args.scene, host=args.host, port=args.port)
        return 0
    except (SceneError, OSError, ValueError) as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
