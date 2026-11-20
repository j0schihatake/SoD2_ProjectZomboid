"""Built-in agent help: what PZMapStudio can do and how to use it."""
from __future__ import annotations

CAPABILITIES = {
    "name": "PZMapStudio",
    "version": "0.1.0",
    "summary": "Command-driven Project Zomboid map editor and real-cell rewriter.",
    "principles": [
        "Scenes are JSON and every change is a command, so an agent can work without a GUI.",
        "Import real compiled cells, edit them, write only the requested layer back.",
        "Original cell headers are copied so rooms, buildings and objects survive.",
        "Audit before export; keep interiors free of grass/road/water.",
    ],
    "commands": {
        "new": "Create an empty scene: pzmapstudio new --name X --width 512 --height 512 --out x.json",
        "import-pz-region": "Import compiled terrain/roads/buildings/furniture for a rectangle.",
        "import-pz-map": "Import a map folder's bounds and spawn points as an overlay.",
        "build-house": "Build a rectangular multi-floor house with rooms and furniture.",
        "build-footprint": "Build a building from a roof/footprint polygon (x,y;x,y;...).",
        "add-floor": "Add a floor to an existing building.",
        "place-furniture": "Place semantic furniture inside a building.",
        "place-object": "Place an exact PZ tile name as an object.",
        "add-road": "Paint a road with material and optional sidewalks.",
        "add-fence": "Add a fence line; --tile writes real fence tiles.",
        "add-roof-access": "Add stairs/ladder access to a building roof.",
        "auto-roof-access": "Add roof access to all large buildings.",
        "add-story": "Mark a randomized-story site.",
        "add-reference": "Attach a photo, map or floor-plan reference to a building.",
        "lookup-address": "Resolve an address via OSM/Nominatim and optionally improvise a bbox building.",
        "lookup-photo": "Find openly licensed Wikimedia photos near an address.",
        "lookup-floorplan": "Search open floor plans for an address.",
        "art-pass": "Clean interiors, clean roads and add roof access in one transaction.",
        "clean-interiors": "Remove outdoor ground from building footprints.",
        "clean-roads": "Make roads/sidewalks win over grass and water.",
        "audit": "Report placement, geometry, spawn and interior-ground problems.",
        "map-save-audit": "Estimate rooms/buildings against the PZ map_meta.bin save buffer.",
        "validate-map": "Check cells, headers, lotpacks, spawns, map.info and save estimate.",
        "layout-audit": "Find duplicate cells and maps disconnected from vanilla/other maps.",
        "find-space": "Find a free compiled-cell block for a new map.",
        "shift-map": "Move a compiled map by whole 256-tile cells.",
        "inspect": "Query only a bbox/layer instead of loading the whole scene.",
        "apply-road-pass": "Rewrite roads/sidewalks in real compiled cells, preserving headers.",
        "apply-object-pass": "Rewrite objects/fences in real compiled cells, preserving headers.",
        "export": "Write a portable bundle: scene JSON, map.info, spawns, objects, optional TMX.",
        "export-pz-region": "Write a terrain-only real .lotheader/.lotpack map folder.",
        "build-catalog": "Build a catalog of tiles/items/story clutter from the game files.",
        "search-catalog": "Search the installed-game asset catalog.",
        "serve": "Start the HTTP API for a live human/agent session.",
        "apply-batch": "Apply a JSON list of commands atomically.",
        "help": "Show this guide; --json returns the machine-readable catalog.",
    },
    "http_api": {
        "GET /api/scene": "whole scene JSON",
        "GET /api/stats": "counts",
        "GET /api/audit": "audit report",
        "GET /api/render.png?floor=0": "preview PNG",
        "POST /api/command": "one command",
        "POST /api/batch": "atomic list of commands",
        "POST /api/save": "persist scene",
    },
    "command_schema": {
        "paint": {"layer": "terrain|roads|sidewalks|water|floors|walls|objects|zones",
                  "x": "int", "y": "int", "w": "int", "h": "int", "tile": "string"},
        "build_house": {"x": "int", "y": "int", "w": "int", "h": "int",
                        "floors": "int", "rooms": "int", "furnish": "bool"},
        "build_footprint": {"points": "[[x,y],...]", "floors": "int", "rooms": "int"},
        "place_object": {"x": "int", "y": "int", "tile": "exact PZ tile"},
        "add_fence": {"x": "int", "y": "int", "length": "int", "axis": "x|y",
                      "tile": "exact PZ fence tile"},
        "add_roof_access": {"building": "id", "x": "int", "y": "int",
                            "z": "int", "to_z": "int", "kind": "stairs|ladder"},
        "add_reference": {"title": "string", "building": "id", "path": "file",
                          "url": "string", "kind": "photo|floorplan|map|other"},
        "add_story": {"x": "int", "y": "int", "w": "int", "h": "int",
                      "kind": "string", "name": "string"},
    },
    "recommended_workflow": [
        "1. lookup-address or import-pz-region.",
        "2. Attach reference photos/floor plans.",
        "3. build-footprint/build-house, add floors/furniture/roof access.",
        "4. art-pass and audit.",
        "5. apply-road-pass/apply-object-pass for real cells.",
        "6. export/package and test in a new save.",
    ],
}


def format_help(json_mode: bool = False) -> str:
    if json_mode:
        import json
        return json.dumps(CAPABILITIES, indent=2, ensure_ascii=False)
    lines = [
        "PZMapStudio — agent command reference",
        "=" * 40,
        f"version: {CAPABILITIES['version']}",
        "",
        CAPABILITIES["summary"],
        "",
        "Commands:",
    ]
    for name, description in CAPABILITIES["commands"].items():
        lines.append(f"  {name:20} {description}")
    lines += ["", "HTTP API:"]
    for name, description in CAPABILITIES["http_api"].items():
        lines.append(f"  {name:24} {description}")
    lines += ["", "Recommended workflow:"]
    lines += [f"  {step}" for step in CAPABILITIES["recommended_workflow"]]
    lines += ["", "Machine-readable: pzmapstudio help --json"]
    return "\n".join(lines)
