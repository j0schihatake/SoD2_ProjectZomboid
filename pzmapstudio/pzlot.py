"""Minimal reader for compiled PZ .lotheader/.lotpack cells.

The format is little-endian and documented in KnoxMap's tools/render_lots.py:

    X_Y.lotheader     "LOTH", version, tile count, tile names,
                      chunk width, chunk height, min level, max level
    world_X_Y.lotpack "LOTP", version, 32*32 chunk offsets, chunk records

This module deliberately only reads. Encoding compiled lots is a separate
milestone; PZMapStudio first needs to import real terrain to edit it.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

CELL = 256
CHUNKS = 32
CHUNK = 8


@dataclass
class Header:
    names: list[str]
    low: int
    high: int
    chunk_width: int
    chunk_height: int
    version: int = 1


def read_header(path: str | Path) -> Header:
    data = Path(path).read_bytes()
    version = 1
    pos = 0
    if data[:4] == b"LOTH":
        version = struct.unpack_from("<i", data, 4)[0]
        pos = 8
    else:
        pos = 4
    (count,) = struct.unpack_from("<i", data, pos)
    pos += 4
    names = []
    for _ in range(count):
        end = data.index(b"\n", pos)
        names.append(data[pos:end].decode("latin-1"))
        pos = end + 1
    chunk_width, chunk_height, low, high = struct.unpack_from("<4i", data, pos)
    return Header(names, low, high, chunk_width, chunk_height, version)


def iter_cell(map_dir: str | Path, cell_x: int, cell_y: int,
              max_level: int | None = None) -> Iterator[tuple[int, int, int, list[str]]]:
    """Yield (absolute tile x, y, z, tile names) for a compiled cell."""
    folder = Path(map_dir)
    header = read_header(folder / f"{cell_x}_{cell_y}.lotheader")
    pack_path = folder / f"world_{cell_x}_{cell_y}.lotpack"
    if not pack_path.exists():
        return
    data = pack_path.read_bytes()
    pos = 4 if data[:4] == b"LOTP" else 0
    pos += 4
    (n,) = struct.unpack_from("<i", data, pos)
    pos += 4
    offsets = struct.unpack_from(f"<{n}q", data, pos)
    high = header.high if max_level is None else min(header.high, max_level)
    for cx in range(CHUNKS):
        for cy in range(CHUNKS):
            p = offsets[cx * CHUNKS + cy]
            if p < 0:
                continue
            bx, by = cx * CHUNK, cy * CHUNK
            skip = 0
            for z in range(header.low, high + 1):
                for sx in range(CHUNK):
                    for sy in range(CHUNK):
                        if skip > 0:
                            skip -= 1
                            continue
                        (count,) = struct.unpack_from("<i", data, p)
                        p += 4
                        if count == -1:
                            (skip,) = struct.unpack_from("<i", data, p)
                            p += 4
                            skip -= 1
                            continue
                        _room = struct.unpack_from("<i", data, p)[0]
                        p += 4
                        if count <= 1:
                            continue
                        ids = struct.unpack_from(f"<{count - 1}i", data, p)
                        p += 4 * (count - 1)
                        names = []
                        for tile_id in ids:
                            if 0 <= tile_id < len(header.names):
                                names.append(header.names[tile_id])
                        if names:
                            yield cell_x * CELL + bx + sx, cell_y * CELL + by + sy, z, names


def classify_tile(names: list[str]) -> tuple[str, str]:
    """Return (layer, representative tile name) for a square."""
    joined = " ".join(names).lower()
    if any(word in joined for word in ("road", "asphalt", "pavement", "sidewalk", "kerb", "street")):
        return "roads", names[0]
    if any(word in joined for word in ("water", "river", "lake")):
        return "water", names[0]
    if any(word in joined for word in ("grass", "dirt", "forest", "ground", "earth")):
        return "terrain", names[0]
    return "terrain", names[0]


def read_header_full(path: str | Path) -> tuple[Header, list[tuple[str, int, list[tuple[int, int, int, int]]]], list[list[int]]]:
    """Read tile names, rooms and buildings from a .lotheader.

    After the tile names the header contains rooms (name, level, rectangles in
    cell-local tile coordinates, objects) and buildings (lists of room indices).
    """
    data = Path(path).read_bytes()
    version = 1
    pos = 0
    if data[:4] == b"LOTH":
        version = struct.unpack_from("<i", data, 4)[0]
        pos = 8
    else:
        pos = 4
    (count,) = struct.unpack_from("<i", data, pos)
    pos += 4
    names = []
    for _ in range(count):
        end = data.index(b"\n", pos)
        names.append(data[pos:end].decode("latin-1"))
        pos = end + 1
    chunk_width, chunk_height, low, high = struct.unpack_from("<4i", data, pos)
    pos += 16
    header = Header(names, low, high, chunk_width, chunk_height, version)
    (nrooms,) = struct.unpack_from("<i", data, pos)
    pos += 4
    rooms = []
    for _ in range(nrooms):
        end = data.index(b"\n", pos)
        name = data[pos:end].decode("latin-1")
        pos = end + 1
        level, nrects = struct.unpack_from("<2i", data, pos)
        pos += 8
        rects = []
        for _ in range(nrects):
            rects.append(struct.unpack_from("<4i", data, pos))
            pos += 16
        (nobj,) = struct.unpack_from("<i", data, pos)
        pos += 4 + 12 * nobj
        rooms.append((name, level, rects))
    (nb,) = struct.unpack_from("<i", data, pos)
    pos += 4
    buildings = []
    for _ in range(nb):
        (nr,) = struct.unpack_from("<i", data, pos)
        pos += 4
        ids = struct.unpack_from(f"<{nr}i", data, pos)
        pos += 4 * nr
        buildings.append(list(ids))
    return header, rooms, buildings


def write_cell(out_dir: str | Path, cell_x: int, cell_y: int,
               tiles: dict[tuple[int, int], str],
               fallback: str = "grass") -> None:
    """Write one 256-tile cell as .lotheader + .lotpack.

    This is a deliberately small terrain-only writer: one level, no rooms, no
    buildings. It exists so a scene edit can be round-tripped through the same
    reader before the full WorldEd bridge is added.
    """
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    names = sorted({fallback, *tiles.values()})
    name_id = {name: index for index, name in enumerate(names)}
    header = bytearray(b"LOTH")
    header += struct.pack("<i", 1)
    header += struct.pack("<i", len(names))
    for name in names:
        header += name.encode("latin-1", errors="replace") + b"\n"
    header += struct.pack("<4i", 8, 8, 0, 0)
    header += struct.pack("<i", 0)  # rooms
    header += struct.pack("<i", 0)  # buildings
    (folder / f"{cell_x}_{cell_y}.lotheader").write_bytes(bytes(header))

    chunks: list[bytes] = []
    for cx in range(CHUNKS):
        for cy in range(CHUNKS):
            chunk = bytearray()
            for z in range(1):  # one level
                for x in range(CHUNK):
                    for y in range(CHUNK):
                        wx = cx * CHUNK + x
                        wy = cy * CHUNK + y
                        tile = tiles.get((wx, wy), fallback)
                        chunk += struct.pack("<iii", 2, 0, name_id[tile])
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
    (folder / f"world_{cell_x}_{cell_y}.lotpack").write_bytes(bytes(pack))


def read_cell_records(map_dir: str | Path, cell_x: int, cell_y: int,
                      max_level: int | None = None):
    """Yield (world x, world y, z, room id, tile names), including room ids."""
    folder = Path(map_dir)
    header = read_header(folder / f"{cell_x}_{cell_y}.lotheader")
    data = (folder / f"world_{cell_x}_{cell_y}.lotpack").read_bytes()
    pos = 4 if data[:4] == b"LOTP" else 0
    pos += 4
    (n,) = struct.unpack_from("<i", data, pos)
    pos += 4
    offsets = struct.unpack_from(f"<{n}q", data, pos)
    high = header.high if max_level is None else min(header.high, max_level)
    for cx in range(CHUNKS):
        for cy in range(CHUNKS):
            p = offsets[cx * CHUNKS + cy]
            if p < 0:
                continue
            bx, by = cx * CHUNK, cy * CHUNK
            skip = 0
            for z in range(header.low, high + 1):
                for sx in range(CHUNK):
                    for sy in range(CHUNK):
                        if skip > 0:
                            skip -= 1
                            continue
                        (count,) = struct.unpack_from("<i", data, p)
                        p += 4
                        if count == -1:
                            (skip,) = struct.unpack_from("<i", data, p)
                            p += 4
                            skip -= 1
                            continue
                        room = struct.unpack_from("<i", data, p)[0]
                        p += 4
                        ids = struct.unpack_from(f"<{count - 1}i", data, p)
                        p += 4 * (count - 1)
                        names = [header.names[i] for i in ids if 0 <= i < len(header.names)]
                        if names:
                            yield (cell_x * CELL + bx + sx,
                                   cell_y * CELL + by + sy, z, room, names)


def _header_with_extra_names(raw: bytes, extra: list[str]) -> bytes:
    """Append tile names to a header without disturbing rooms/buildings."""
    if not extra:
        return raw
    pos = 8 if raw[:4] == b"LOTH" else 4
    (count,) = struct.unpack_from("<i", raw, pos)
    names_start = pos + 4
    cursor = names_start
    for _ in range(count):
        cursor = raw.index(b"\n", cursor) + 1
    tail = raw[cursor:]
    names = raw[names_start:cursor]
    extra_bytes = b"".join(name.encode("latin-1", errors="replace") + b"\n" for name in extra)
    return raw[:pos] + struct.pack("<i", count + len(extra)) + names + extra_bytes + tail


def rewrite_cell(source_dir: str | Path, out_dir: str | Path,
                 cell_x: int, cell_y: int,
                 overrides: dict[tuple[int, int, int], list[str]],
                 strip_rooms: bool = False) -> None:
    """Rewrite one cell's lotpack while copying its lotheader verbatim.

    Keeping the original header preserves rooms, buildings and object metadata.
    Tile overrides must use names already present in that header, so this is a
    safe terrain/road editor rather than a header rebuild.
    """
    source = Path(source_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    header_path = source / f"{cell_x}_{cell_y}.lotheader"
    header = read_header(header_path)
    extra = sorted({name for names in overrides.values() for name in names}
                   - set(header.names))
    names_all = header.names + extra
    if strip_rooms:
        # Keep the tile table and level range, drop room/building metadata.
        header_bytes = bytearray(b"LOTH")
        header_bytes += struct.pack("<i", header.version)
        header_bytes += struct.pack("<i", len(names_all))
        for name in names_all:
            header_bytes += name.encode("latin-1", errors="replace") + b"\n"
        header_bytes += struct.pack("<4i", header.chunk_width, header.chunk_height,
                                     header.low, header.high)
        header_bytes += struct.pack("<i", 0)  # rooms
        header_bytes += struct.pack("<i", 0)  # buildings
        header_bytes = bytes(header_bytes)
    else:
        header_bytes = _header_with_extra_names(header_path.read_bytes(), extra)
    name_id = {name: index for index, name in enumerate(names_all)}
    records: dict[tuple[int, int], list[tuple[int, int, int, list[int]]]] = {}
    for wx, wy, z, room, names in read_cell_records(source, cell_x, cell_y):
        key = (wx, wy, z)
        chosen = overrides.get(key, names)
        ids = [name_id[name] for name in chosen if name in name_id]
        if not ids:
            continue
        if strip_rooms:
            room = 0
        lx, ly = wx - cell_x * CELL, wy - cell_y * CELL
        cx, cy = lx // CHUNK, ly // CHUNK
        records.setdefault((cx, cy), []).append((z, lx % CHUNK, ly % CHUNK, [room] + ids))
    chunks: dict[tuple[int, int], bytes] = {}
    for cx in range(CHUNKS):
        for cy in range(CHUNKS):
            chunk = bytearray()
            pending: dict[tuple[int, int, int], list[int]] = {
                (z, x, y): ids for z, x, y, ids in records.get((cx, cy), [])
            }
            # The pack reader expects every square of every level in a chunk,
            # even when the square is empty. Empty squares are a skip run.
            skip = 0
            for z in range(header.low, header.high + 1):
                for x in range(CHUNK):
                    for y in range(CHUNK):
                        ids = pending.get((z, x, y))
                        if ids is None:
                            skip += 1
                            continue
                        if skip:
                            chunk += struct.pack("<ii", -1, skip)
                            skip = 0
                        chunk += struct.pack("<i", len(ids))
                        chunk += struct.pack(f"<{len(ids)}i", *ids)
            if skip:
                chunk += struct.pack("<ii", -1, skip)
            chunks[(cx, cy)] = bytes(chunk)
    base = 4 + 4 + 4 + CHUNKS * CHUNKS * 8
    offsets = []
    position = base
    for cx in range(CHUNKS):
        for cy in range(CHUNKS):
            chunk = chunks[(cx, cy)]
            if not chunk:
                offsets.append(-1)
            else:
                offsets.append(position)
                position += len(chunk)
    pack = bytearray(b"LOTP")
    pack += struct.pack("<i", 1)
    pack += struct.pack("<i", CHUNKS * CHUNKS)
    pack += struct.pack(f"<{CHUNKS * CHUNKS}q", *offsets)
    for cx in range(CHUNKS):
        for cy in range(CHUNKS):
            pack += chunks[(cx, cy)]
    (out / f"{cell_x}_{cell_y}.lotheader").write_bytes(header_bytes)
    (out / f"world_{cell_x}_{cell_y}.lotpack").write_bytes(bytes(pack))


def read_edge_roads(map_dir: str | Path, cell_x: int, cell_y: int,
                    side: str) -> set[int]:
    """Read road positions on one cell edge without scanning the whole cell.

    Returns the coordinate along the edge (y for west/east, x for north/south).
    """
    folder = Path(map_dir)
    header = read_header(folder / f"{cell_x}_{cell_y}.lotheader")
    data = (folder / f"world_{cell_x}_{cell_y}.lotpack").read_bytes()
    pos = 4 if data[:4] == b"LOTP" else 0
    pos += 4
    (n,) = struct.unpack_from("<i", data, pos)
    pos += 4
    offsets = struct.unpack_from(f"<{n}q", data, pos)
    chunks_x = range(0, 1) if side == "west" else range(CHUNKS - 1, CHUNKS) if side == "east" else range(CHUNKS)
    chunks_y = range(0, 1) if side == "north" else range(CHUNKS - 1, CHUNKS) if side == "south" else range(CHUNKS)
    found: set[int] = set()
    for cx in chunks_x:
        for cy in chunks_y:
            p = offsets[cx * CHUNKS + cy]
            if p < 0:
                continue
            skip = 0
            for z in range(header.low, header.high + 1):
                for sx in range(CHUNK):
                    for sy in range(CHUNK):
                        if skip > 0:
                            skip -= 1
                            continue
                        (count,) = struct.unpack_from("<i", data, p)
                        p += 4
                        if count == -1:
                            (skip,) = struct.unpack_from("<i", data, p)
                            p += 4
                            skip -= 1
                            continue
                        p += 4  # room id
                        if count <= 1:
                            continue
                        ids = struct.unpack_from(f"<{count - 1}i", data, p)
                        p += 4 * (count - 1)
                        names = [header.names[i] for i in ids if 0 <= i < len(header.names)]
                        if not any(("street" in n or "road" in n or "asphalt" in n) for n in names):
                            continue
                        lx, ly = cx * CHUNK + sx, cy * CHUNK + sy
                        if side == "west" and lx == 0:
                            found.add(ly)
                        elif side == "east" and lx == 255:
                            found.add(ly)
                        elif side == "north" and ly == 0:
                            found.add(lx)
                        elif side == "south" and ly == 255:
                            found.add(lx)
    return found
