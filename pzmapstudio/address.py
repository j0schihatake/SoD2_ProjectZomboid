"""Address lookup and reference links.

Google Maps/Street View cannot legally be bulk-scraped or cached by a map tool.
This module resolves an address through OpenStreetMap's Nominatim, builds a
human-openable Google Maps link, and optionally reads building tags/footprint.
A user-supplied photo remains the best reference for facade details.
"""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "PZMapStudio/0.1 (community Project Zomboid map editor)"


class AddressError(RuntimeError):
    pass


@dataclass
class AddressResult:
    query: str
    display_name: str
    lat: float
    lon: float
    boundingbox: list[float]
    tags: dict

    def to_dict(self) -> dict:
        return {"query": self.query, "display_name": self.display_name,
                "lat": self.lat, "lon": self.lon,
                "boundingbox": self.boundingbox, "tags": self.tags}


def google_maps_url(query: str) -> str:
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(query)


def parse_nominatim(query: str, payload: list[dict]) -> AddressResult:
    if not payload:
        raise AddressError(f"address not found: {query}")
    item = payload[0]
    return AddressResult(
        query=query,
        display_name=str(item.get("display_name", query)),
        lat=float(item["lat"]),
        lon=float(item["lon"]),
        boundingbox=[float(v) for v in item.get("boundingbox", [])],
        tags=dict(item.get("extratags") or {}),
    )


def geocode(address: str, timeout: int = 20) -> AddressResult:
    params = urllib.parse.urlencode({
        "q": address, "format": "jsonv2", "limit": 1,
        "addressdetails": 1, "extratags": 1,
    })
    request = urllib.request.Request(
        f"{NOMINATIM}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as error:  # network/HTTP/JSON
        raise AddressError(f"geocoding failed: {error}") from error
    return parse_nominatim(address, payload)


def footprint_dimensions(result: AddressResult, meters_per_tile: float = 2.0,
                         default_floors: int = 2) -> dict:
    """Estimate a rectangular footprint from the Nominatim bounding box.

    This is an improvisation when no photo is available: the real OSM
    footprint is better, but the bounding box still gives a believable
    silhouette and orientation for a first massing pass.
    """
    if len(result.boundingbox) != 4:
        raise AddressError("no bounding box in address result")
    south, north, west, east = result.boundingbox
    lat_m = abs(north - south) * 111_320
    lon_m = abs(east - west) * 111_320 * math.cos(math.radians((north + south) / 2))
    floors = int(result.tags.get("building:levels", default_floors))
    return {
        "width_m": round(lon_m, 1),
        "height_m": round(lat_m, 1),
        "width_tiles": max(6, int(lon_m / meters_per_tile)),
        "height_tiles": max(6, int(lat_m / meters_per_tile)),
        "floors": max(1, floors),
        "material": result.tags.get("building:material", ""),
        "roof": result.tags.get("roof:shape", ""),
    }


COMMONS_API = "https://commons.wikimedia.org/w/api.php"


def wikimedia_photos(lat: float, lon: float, radius: int = 500,
                     limit: int = 5, timeout: int = 20) -> list[dict]:
    """Find openly licensed Wikimedia Commons photos near a coordinate."""
    params = urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "geosearch",
        "ggscoord": f"{lat}|{lon}", "ggsradius": radius, "ggslimit": limit,
        "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 800,
    })
    request = urllib.request.Request(
        f"{COMMONS_API}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        raise AddressError(f"Wikimedia lookup failed: {error}") from error
    pages = (payload.get("query") or {}).get("pages") or {}
    results = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        results.append({
            "title": page.get("title", ""),
            "url": url,
            "descriptionurl": info.get("descriptionurl", ""),
            "license": (info.get("extmetadata") or {}).get("LicenseShortName", {}).get("value", ""),
        })
    return results


def download_photo(url: str, path: str | Path, timeout: int = 30) -> Path:
    from pathlib import Path
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
    except Exception as error:
        raise AddressError(f"photo download failed: {error}") from error
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out


def wikimedia_search(query: str, limit: int = 5, timeout: int = 20) -> list[dict]:
    """Search Wikimedia Commons files, e.g. for a building floor plan."""
    params = urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": limit,
        "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 1200,
    })
    request = urllib.request.Request(
        f"{COMMONS_API}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        raise AddressError(f"Wikimedia search failed: {error}") from error
    pages = (payload.get("query") or {}).get("pages") or {}
    results = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        results.append({
            "title": page.get("title", ""),
            "url": url,
            "descriptionurl": info.get("descriptionurl", ""),
            "license": (info.get("extmetadata") or {}).get("LicenseShortName", {}).get("value", ""),
        })
    return results
