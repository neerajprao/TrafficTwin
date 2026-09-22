"""
Phase 2 (rebuilt) - fetches a real satellite/aerial image of the Astra Biz
Center junction (free Esri World Imagery XYZ tiles) and stitches it into one
cached background image, so the digital twin renders on top of the actual
place instead of a bare schematic. Fetched once and cached to disk; a
PixelMapper then converts any lon/lat into on-screen pixel coordinates.
"""
import io
import json
import math
import os

import requests
from PIL import Image

TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
TILE_SIZE = 256
ZOOM = 18
PADDING_DEG = 0.0006  # small margin so entry/exit nodes aren't flush with the edge
CACHE_PATH = "data/basemap/astra_biz_center.png"


def _deg2num(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    xtile = (lon + 180.0) / 360.0 * n
    ytile = (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return xtile, ytile


def _num2deg(xtile: float, ytile: float, zoom: int) -> tuple[float, float]:
    n = 2.0 ** zoom
    lon = xtile / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * ytile / n))))
    return lat, lon


class PixelMapper:
    """Maps lon/lat to raw (unscaled) basemap-image pixel coordinates - the
    same space the stitched satellite image is in. A Camera (see render.py)
    layers window-fit scale plus any user pan/zoom on top of this."""

    def __init__(self, zoom: int, origin_xtile: float, origin_ytile: float, center_lat: float):
        self.zoom = zoom
        self.origin_xtile = origin_xtile
        self.origin_ytile = origin_ytile
        self.meters_per_pixel = 156543.03392 * math.cos(math.radians(center_lat)) / (2 ** zoom)

    def to_pixel(self, lon: float, lat: float) -> tuple[float, float]:
        xt, yt = _deg2num(lat, lon, self.zoom)
        raw_x = (xt - self.origin_xtile) * TILE_SIZE
        raw_y = (yt - self.origin_ytile) * TILE_SIZE
        return raw_x, raw_y

    def to_lonlat(self, raw_x: float, raw_y: float) -> tuple[float, float]:
        """Inverse of to_pixel - turns a raw basemap-image pixel (e.g. from
        a mouse click, after undoing the Camera transform) back into a real
        (lon, lat), for the road editor."""
        xt = raw_x / TILE_SIZE + self.origin_xtile
        yt = raw_y / TILE_SIZE + self.origin_ytile
        lat, lon = _num2deg(xt, yt, self.zoom)
        return lon, lat


def _tile_extent(bounds: tuple[float, float, float, float], zoom: int) -> tuple[int, int, int, int]:
    """(xtile_min, ytile_min, xtile_max, ytile_max) covering `bounds` plus
    PADDING_DEG - the exact tile grid _stitch_tiles fetches, and the same
    thing load_basemap needs to know is still covered by a cached image
    before trusting it (see load_basemap's docstring)."""
    min_lon, min_lat, max_lon, max_lat = bounds
    min_lon -= PADDING_DEG
    max_lon += PADDING_DEG
    min_lat -= PADDING_DEG
    max_lat += PADDING_DEG

    x1, y1 = _deg2num(max_lat, min_lon, zoom)  # top-left
    x2, y2 = _deg2num(min_lat, max_lon, zoom)  # bottom-right
    return int(x1), int(y1), int(x2), int(y2)


def _stitch_tiles(bounds: tuple[float, float, float, float], zoom: int) -> tuple[Image.Image, float, float]:
    xtile_min, ytile_min, xtile_max, ytile_max = _tile_extent(bounds, zoom)

    cols = xtile_max - xtile_min + 1
    rows = ytile_max - ytile_min + 1
    print(f"Fetching {cols}x{rows} = {cols * rows} satellite tiles at zoom {zoom}...")

    composite = Image.new("RGB", (cols * TILE_SIZE, rows * TILE_SIZE))
    session = requests.Session()
    for row, ytile in enumerate(range(ytile_min, ytile_max + 1)):
        for col, xtile in enumerate(range(xtile_min, xtile_max + 1)):
            url = TILE_URL.format(z=zoom, x=xtile, y=ytile)
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            tile = Image.open(io.BytesIO(resp.content)).convert("RGB")
            composite.paste(tile, (col * TILE_SIZE, row * TILE_SIZE))

    return composite, float(xtile_min), float(ytile_min)


def _meta_path(cache_path: str) -> str:
    return cache_path + ".meta.json"


def load_basemap(bounds: tuple[float, float, float, float], zoom: int = ZOOM,
                  cache_path: str = CACHE_PATH) -> tuple[Image.Image, float, float]:
    """Returns (stitched image, origin_xtile, origin_ytile). Cached to disk
    after the first fetch - but the cache is only trusted if it actually
    covers the requested tile extent at the requested zoom (recorded in a
    small sidecar .meta.json next to the image). Without this check, a
    network that's moved (twin/editor.py's move-network mode - see
    NetworkData.bounds, recomputed on every edit) would silently keep using
    stale tiles fetched for the old location: origin_xtile/ytile would be
    recomputed fresh from the new bounds, but the actual pixels underneath
    would still be the old place, drifting the two apart by however far the
    network moved - exactly the "my edits aren't really being saved"
    symptom this was written to fix, since the road data was fine all
    along and only the picture underneath it was wrong."""
    xtile_min, ytile_min, xtile_max, ytile_max = _tile_extent(bounds, zoom)
    meta_path = _meta_path(cache_path)

    if os.path.exists(cache_path) and os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        if (meta.get("zoom") == zoom and meta.get("xtile_min") == xtile_min
                and meta.get("ytile_min") == ytile_min and meta.get("xtile_max") == xtile_max
                and meta.get("ytile_max") == ytile_max):
            return Image.open(cache_path).convert("RGB"), float(xtile_min), float(ytile_min)
        print("Cached satellite image no longer covers the current network bounds - refetching...")

    image, origin_xtile, origin_ytile = _stitch_tiles(bounds, zoom)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    image.save(cache_path)
    with open(meta_path, "w") as f:
        json.dump({"zoom": zoom, "xtile_min": xtile_min, "ytile_min": ytile_min,
                   "xtile_max": xtile_max, "ytile_max": ytile_max}, f)
    return image, origin_xtile, origin_ytile
