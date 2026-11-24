"""Rebuild the dated RGB reference and independent spectral check for Yalova."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
import json
import math

import numpy as np
from PIL import Image
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds, from_origin
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds


ROOT = Path(__file__).resolve().parents[1]
DATE = "2026-11-09"
BOUNDS = (28.70, 40.44, 29.69, 40.77)
CATALOG = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-c1-l2a"
NODATA = -9999.0


def load_json(url):
    with urlopen(url, timeout=60) as response:
        return json.load(response)


def read_asset(item, name, grid):
    asset = item["assets"][name]
    resampling = Resampling.nearest if name == "scl" else Resampling.bilinear
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="60",
                      GDAL_HTTP_MAX_RETRY="2"), rasterio.open(asset["href"]) as source:
        with WarpedVRT(source, resampling=resampling, **grid) as warped:
            data = warped.read()
    if name in ("scl", "visual"):
        return data
    band = asset["raster:bands"][0]
    stored = data[0]
    value = stored.astype("float32") * band["scale"] + band["offset"]
    value[stored == band["nodata"]] = np.nan
    return value


def main():
    static = ROOT / "static"
    layers = ROOT / "layers"
    static.mkdir(exist_ok=True)
    layers.mkdir(exist_ok=True)
    query = urlencode({"collections": COLLECTION, "bbox": ",".join(map(str, BOUNDS)),
                       "datetime": f"{DATE}T00:00:00Z/{DATE}T23:59:59Z", "limit": 50})
    items = load_json(f"{CATALOG}/search?{query}")["features"]
    # One orbit and a common tile zone suffice for the entire frame. Sorting
    # fixes the choice of source pixels in neighbouring tiles' overlap strips.
    items = sorted([item for item in items if item["properties"]["proj:epsg"] == 32635
                    and item["properties"]["platform"] == "sentinel-2c"],
                   key=lambda item: item["id"])
    if {item["properties"]["mgrs:grid_square"] for item in items} != {"PE", "PF", "QE", "QF"}:
        raise RuntimeError("The expected four same-orbit granules are unavailable.")
    width, height = 1900, 835
    rgb_grid = dict(crs="EPSG:4326", transform=from_bounds(*BOUNDS, width, height),
                    width=width, height=height)
    rgb = np.zeros((3, height, width), dtype="uint8")
    left, bottom, right, top = transform_bounds("EPSG:4326", "EPSG:32635", *BOUNDS)
    scale = 60
    west = math.floor(left / scale) * scale
    north = math.ceil(top / scale) * scale
    iw, ih = math.ceil((right - west) / scale), math.ceil((north - bottom) / scale)
    grid = dict(crs="EPSG:32635", transform=from_origin(west, north, scale, scale),
                width=iw, height=ih)
    indices = np.full((3, ih, iw), NODATA, dtype="float32")
    for item in items:
        print("Reading", item["id"], flush=True)
        with ThreadPoolExecutor(max_workers=6) as pool:
            jobs = {key: pool.submit(read_asset, item, key, rgb_grid if key == "visual" else grid)
                    for key in ("visual", "scl", "green", "red", "nir", "swir16")}
            bands = {key: job.result() for key, job in jobs.items()}
        tci = bands["visual"]
        fill = ~rgb.any(axis=0) & tci.any(axis=0)
        rgb[:, fill] = tci[:, fill]
        clear = np.isin(bands["scl"][0], (4, 5, 6))
        for idx, (a, b) in enumerate([("nir", "red"), ("swir16", "nir"), ("green", "swir16")]):
            first, second = bands[a], bands[b]
            total = first + second
            # Negative retrieved reflectance over dark water can yield unbounded
            # ratios. Retain only physical, non-negative inputs with a usable sum.
            take = (indices[idx] == NODATA) & clear & (first >= 0) & (second >= 0) & (total > 1e-5)
            indices[idx, take] = (first[take] - second[take]) / total[take]
    # Inside the rectangular scene the RGB is the provider's optical image;
    # clouds remain visible. No online tiles are needed for the app overlay.
    # Lift shadows from the low November sun uniformly across all three channels.
    curve = np.rint(255 * (np.arange(256) / 255) ** 0.80).astype("uint8")
    Image.fromarray(curve[rgb.transpose(1, 2, 0)]).save(static / "yalova_rgb.jpg", quality=92)
    names = ("ndvi", "ndbi", "mndwi")
    with rasterio.open(layers / "copernicus_indices_reference.tif", "w", driver="GTiff",
                       count=3, dtype="float32", compress="deflate", predictor=3,
                       tiled=True, nodata=NODATA, **grid) as dst:
        dst.write(indices)
        dst.descriptions = names
        dst.update_tags(source="Copernicus Sentinel-2C L2A, Earth Search Collection 1",
                        acquisition_date=DATE, scl_classes="4,5,6", units="ratio")
    stamp = {
        "bounds": [[BOUNDS[1], BOUNDS[0]], [BOUNDS[3], BOUNDS[2]]],
        "date": DATE, "credit": "Contains modified Copernicus Sentinel data (2026).",
        "platform": "Sentinel-2C MSI Level-2A", "crs": "EPSG:4326",
        "size_pixels": [width, height],
        "rgb_footprint_percent": round(float(rgb.any(axis=0).mean() * 100), 2),
        "rgb_bands": ["B04", "B03", "B02"],
        "display_curve": "RGB output = 255 * (8-bit TCI / 255)^0.80, applied equally to each channel.",
        "source": "Original Copernicus level-2A true-colour image mosaicked from a single orbit, served as Earth Search Collection 1 COGs.",
        "items": [
            {"earth_search": f"{CATALOG}/collections/{COLLECTION}/items/{item['id']}",
             "copernicus": "https://stac.dataspace.copernicus.eu/v1/collections/sentinel-2-l2a/items/"
                + item["properties"]["s2:product_uri"].removesuffix(".SAFE"),
             "tile": item["properties"]["mgrs:grid_square"],
             "time_utc": item["properties"]["datetime"]} for item in items],
        "independent_check": {"filename": "copernicus_indices_reference.tif",
                              "native_grid_m": {"green_red_nir": 10, "swir_scl": 20},
                              "output_grid_m": scale, "crs": "EPSG:32635", "nodata": NODATA,
                              "bands": list(names),
                              "coverage_percent_of_padded_projected_rectangle":
                                  {name: round(float((arr != NODATA).mean()*100), 2)
                                   for name, arr in zip(names, indices)}}
    }
    (layers / "rgb_bounds.json").write_text(json.dumps(stamp, indent=2), encoding="utf-8")
    print(json.dumps(stamp, indent=2))


if __name__ == "__main__":
    main()
