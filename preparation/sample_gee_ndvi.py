"""Measure mean NDVI inside complete 100 m buffers around verified parcels."""
import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from shapely.geometry import box, mapping


def sample(points_file, raster_file, output_file):
    points = gpd.read_file(points_file).to_crs("EPSG:32635")
    records = []
    with rasterio.open(raster_file) as source:
        if source.count != 1:
            raise ValueError("Expected the single-band Earth Engine NDVI image.")
        pixels = source.read(1, masked=True)
        valid = (~np.ma.getmaskarray(pixels) & np.isfinite(pixels.data)
                 & (pixels.data >= -1) & (pixels.data <= 1))
        footprints = points.geometry.buffer(100).to_crs(source.crs)
        extent = box(*source.bounds)
        for index, footprint in footprints.items():
            if not extent.covers(footprint):
                continue
            inside = geometry_mask([mapping(footprint)], out_shape=source.shape,
                                   transform=source.transform, invert=True)
            usable = inside & valid
            if usable.any():
                records.append({
                    "record_key": points.at[index, "record_key"],
                    "gee_ndvi_100m": float(pixels.data[usable].mean()),
                    "valid_pixels": int(usable.sum()),
                    "pixel_centres": int(inside.sum()),
                })
    pd.DataFrame(records, columns=["record_key", "gee_ndvi_100m", "valid_pixels",
                                   "pixel_centres"]).to_csv(output_file, index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verified_points", type=Path)
    parser.add_argument("ndvi_geotiff", type=Path)
    parser.add_argument("output_csv", type=Path)
    args = parser.parse_args()
    sample(args.verified_points, args.ndvi_geotiff, args.output_csv)
