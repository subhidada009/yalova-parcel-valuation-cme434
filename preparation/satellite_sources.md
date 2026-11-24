# Satellite evidence for Yalova

## Dated optical view

The full-frame map background uses a single Sentinel-2C overpass on **9 November 2026**. The four Level-2A granules in UTM zone 35 cover the entire terrestrial province. They were acquired between 08:58:52 and 08:59:10 UTC. Their Copernicus product IDs, Earth Search item links, bounds and display parameters are recorded in `layers/rgb_bounds.json`. The original true-colour product uses red B04, green B03 and blue B02. The image has a common shadow-lifting curve for the three channels. Clouds are visible near the eastern shore. [Copernicus granule record](https://stac.dataspace.copernicus.eu/v1/collections/sentinel-2-l2a/items/S2C_MSIL2A_20261109T085151_N0513_R107_T35TPF_20261109T123110)

Brave was also used to view the **9 November 2026** acquisition over Yalova in a publicly hosted Google Earth Engine app. The filters in the recorded view span 9 November to the exclusive end date of 10 November. A pale street map shows through on the north coast where this viewer has a gap. The full-frame map background assembles all four matching Copernicus granules. A second one-day view on 22 October 2026 shows the full peninsula in the same Earth Engine viewer. The original English-language screen captures for both dates are in the analysis directory. [Earth Engine Sentinel 2 Explorer](https://jackdmay.users.earthengine.app/view/sentinel-2-explorer)

## Spectral check distributed with the project

`layers/copernicus_indices_reference.tif` contains single-date NDVI, NDBI and MNDWI, in that order. These independently computed values let a reader inspect the local landscape before training. They are dimensionless. Reflectance is calculated using each asset's Collection 1 scale and offset. Cloud screening retains Sentinel scene classes 4, 5 and 6. Ratios require non-negative reflectance and a positive denominator. Bilinear reflectance resampling and nearest-neighbour scene classification produce a 60 m UTM 35N cross-check. At the centres of 218,788 grid pixels inside the terrestrial boundary, usable coverage is 90.53% for NDVI, 90.60% for NDBI and 90.62% for MNDWI. Unusable cells carry the value -9999. The separate rectangular-frame coverage in the JSON includes dark sea pixels. [Collection 1 processing documentation](https://github.com/Element84/earth-search/blob/main/docs/collections/sentinel-2-l2a.md)

To reproduce the optical background, the bounds sidecar and the independent index raster, run `python preparation/copernicus_reference.py` from the repository root. To regenerate the three-panel index map and summary table, run `python preparation/plot_spectral_reference.py`. These are saved to `analysis/spectral_reference.png` and `analysis/spectral_reference.csv`. The observed medians at valid land pixels are 0.7425 for NDVI, −0.1961 for NDBI and −0.5979 for MNDWI. The data preparation step reads the public archive. The Web GIS reads the saved outputs locally. Imagery contains modified Copernicus Sentinel data (2026).

## Six environmental features for model training

Run `preparation/earth_engine.js` in the Earth Engine Code Editor under a registered project. The scene shown on screen has its acquisition date in a map label. Run the three tasks in the Tasks pane, then retrieve the results from the `CME434_Yalova` folder in Google Drive.

| Output | Use |
|---|---|
| `environment.tif` | Place in `layers/`. The backend expects six ordered Float32 bands in EPSG:32635. |
| `sentinel2_rgb_2026-11-09.tif` | Full-region, single-date RGB rendered in Earth Engine. |
| `satellite_inventory.csv` | Keep in `layers/` with dates, collection IDs and acquisition IDs for the export. Each row identifies a candidate granule and its role in the workflow. |

The optical indices and land probabilities use a window from **25 October through 23 November 2026 UTC**. The composite uses a temporal median for each pixel and band. The output is sampled on a 30 m projected grid. The backend calculates each feature as the arithmetic mean of valid pixel centres in the listing's 100 m buffer. This distinguishes the time reduction from the spatial average.

| Band | Meaning | Inputs |
|---|---|---|
| `ndvi` | Vegetation signal | (B08 − B04) / (B08 + B04) |
| `ndbi` | Built-up spectral signal | (B11 − B08) / (B11 + B08) |
| `mndwi` | Surface-water signal | (B03 − B11) / (B03 + B11) |
| `built_probability` | Probability of the Dynamic World built class | built |
| `tree_probability` | Probability of the Dynamic World trees class | trees |
| `crop_probability` | Probability of the Dynamic World crops class | crops |

Sentinel B03, B04 and B08 have native 10 m pixels. B11 and scene classification have 20 m pixels. The script harmonises the spectral grids on each granule's 20 m grid before deriving ratios. Dynamic World probabilities originate on a 10 m grid with the provider's cloud and shadow masking. The three probabilities describe separate classes and are bounded between zero and one. The imagery records vegetation, materials and land cover at the sensor's spatial and temporal support. Narrow or mixed-use parcels can include neighbouring land in their 100 m mean. [Sentinel-2 surface reflectance](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED) · [Dynamic World V1](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1)

The numerical six-band export requires access to a registered Earth Engine project. Its production status is recorded separately from the completed visual and spectral check. For released Dynamic World derivatives use the provider attribution “This dataset is produced for the Dynamic World Project by Google in partnership with National Geographic Society and the World Resources Institute.” Dynamic World is available under CC BY 4.0. [Dataset terms and scientific reference](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1)
