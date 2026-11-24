"""Describe clear-pixel conditions inside the province on 9 November 2026."""

from pathlib import Path
import csv
import json

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from shapely.geometry import shape


ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    ("NDVI", "Vegetation", ["#76543a", "#ddc79c", "#f6efcf", "#67a675", "#11553a"]),
    ("NDBI", "Built-up signal", ["#275d70", "#86b2b9", "#f6f1db", "#d29066", "#8b4239"]),
    ("MNDWI", "Water signal", ["#815b33", "#d2b37c", "#f3efda", "#74b9be", "#116076"]),
)


def main():
    directory = ROOT / "analysis"
    directory.mkdir(exist_ok=True)
    features = json.loads((ROOT / "layers/boundary.geojson").read_text(encoding="utf-8"))["features"]
    with rasterio.open(ROOT / "layers/copernicus_indices_reference.tif") as src:
        polygons = [transform_geom("EPSG:4326", src.crs, f["geometry"]) for f in features]
        domain = geometry_mask(polygons, src.shape, src.transform, invert=True)
        stack = src.read(masked=True)
        bounds = src.bounds
    extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
    figure, axes = plt.subplots(3, 1, figsize=(9.0, 9.6))
    figure.subplots_adjust(left=0.05, right=0.84, bottom=0.11, top=0.86, hspace=0.24)
    rows = []
    for ax, band, (name, title, palette) in zip(axes, stack, NAMES):
        data = np.ma.array(band, mask=np.ma.getmaskarray(band) | ~domain)
        vals = data.compressed()
        q25, median, q75 = np.percentile(vals, [25, 50, 75])
        rows.append(dict(index=name, land_centres=int(domain.sum()), valid_centres=int(vals.size),
                         valid_percent=round(100 * vals.size / domain.sum(), 2),
                         p25=round(float(q25), 4), median=round(float(median), 4),
                         p75=round(float(q75), 4)))
        ax.imshow(np.ma.masked_where(~domain, np.ones_like(data, dtype=float)), extent=extent,
                  cmap=LinearSegmentedColormap.from_list("missing", ["#d9dee0", "#d9dee0"]),
                  interpolation="nearest", vmin=0, vmax=1)
        colors = LinearSegmentedColormap.from_list(name, palette)
        mapped = ax.imshow(data, extent=extent, vmin=-1, vmax=1, cmap=colors, interpolation="nearest")
        for polygon in polygons:
            geom = shape(polygon)
            for part in (geom.geoms if geom.geom_type == "MultiPolygon" else [geom]):
                ax.plot(*part.exterior.xy, color="#4c5c5e", lw=0.45)
        ax.set_xlim(648000, 720000)
        ax.set_ylim(4479000, 4515500)
        ax.set_aspect("equal")
        ax.set_axis_off()
        ax.set_title(f"{name}   {title}", loc="left", fontweight="bold", color="#263c3b", fontsize=13)
        box = ax.get_position()
        cax = figure.add_axes([box.x1+0.03, box.y0+box.height*0.11, 0.012, box.height*0.72])
        bar = figure.colorbar(mapped, cax=cax, ticks=[-1, 0, 1])
        bar.outline.set_visible(False)
        bar.ax.tick_params(length=0, labelsize=9)
        ax.text(0.01, 0.015, f"Median {median:.2f}", transform=ax.transAxes, fontsize=9)
        # The projected coordinate grid supplies the bar length in metres.
        ax.plot([705500, 715500], [4480800, 4480800], lw=2.0, color="#253d3d")
        ax.text(710500, 4481700, "10 km", ha="center", fontsize=8)
    figure.text(0.08, 0.965, "Spectral conditions across Yalova Province", fontsize=19,
                color="#183d3b", fontweight="bold")
    figure.text(0.08, 0.931, "Sentinel-2C  ·  9 November 2026  ·  60 m grid  ·  North up",
                fontsize=10, color="#465e60")
    figure.legend(handles=[Patch(facecolor="#d9dee0", label="Cloud, shadow or invalid reflectance")],
                  frameon=False, loc="lower left", bbox_to_anchor=(0.066, 0.060), fontsize=9)
    figure.text(0.08, 0.044, "Medians use valid pixel centres inside the terrestrial study boundary.",
                fontsize=8, color="#485252")
    figure.text(0.08, 0.022, "Contains modified Copernicus Sentinel data (2026). Boundary © OpenStreetMap contributors.",
                fontsize=8, color="#485252")
    figure.savefig(directory / "spectral_reference.png", dpi=150, facecolor="white")
    plt.close(figure)
    with (directory / "spectral_reference.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
