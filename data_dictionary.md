# Data dictionary

CME434 · Yalova Province · 23 November 2026. Each private regression record represents one manually verified listing. WGS84 uses longitude first in GeoJSON. All metric operations use EPSG:32635. Date columns use YYYY-MM-DD. Currency is nominal Turkish lira.

## Private collection, keys and target

| Column | Unit / representation | Source and meaning |
|---|---|---|
| ilan_no | text | Original advertisement number, preserved as text. Private appendix and analytical tables only. |
| url | absolute URL | Publicly visible listing reference recorded manually. Private. |
| record_key | text | Deterministic pseudonym from site hostname and ad number for joins in the application. |
| ad_date | date | Posting date displayed in the ad. |
| collected_on | date | Day the group reviewed and recorded the ad. |
| latitude, longitude | decimal degrees | WGS84 centroid checked on the parcel map; no neighbourhood centroids. |
| coordinate_basis | text | “Parcel centroid on listing map” or “Verified cadastral parcel centroid”. |
| x, y | m | UTM zone 35N easting and northing transformed from the listing's WGS84 coordinates. |
| price_tl | TL | Total asking price as listed. |
| kimden | category | Owner, Agency, Developer, Bank, Public institution, Other or Unknown. No personal names or contacts. |
| unit_tl_m2 | TL/m² | Label = price_tl / area_m2. Prices, dates, URLs and IDs are excluded from the predictors. |
| geometry | point | Parcel centroid; WGS84 in GeoJSON and projected UTM in GPKG/SHP. |

## Eighteen model predictors

| Column | Unit | Source, date and spatial support |
|---|---|---|
| area_m2 | m² | Advertised parcel area on the recorded posting date, parcel support. |
| imar_durumu | category | Advertised zoning / development status, posting date, parcel support. Use consistent English categories. |
| emsal | ratio | Advertised KAKS / floor-area ratio, posting date, parcel support. |
| gabari_m | m | Advertised permitted building height, posting date, parcel support. Leave free-text or unspecified heights missing. |
| tapu_durumu | category | Advertised deed status, posting date, parcel support. |
| ndvi | unitless | (B8−B4)/(B8+B4), Sentinel-2 SR Harmonized; NIR/red both 10 m native. |
| ndbi | unitless | (B11−B8)/(B11+B8), Sentinel-2 SR Harmonized; SWIR 20 m and NIR 10 m native. |
| mndwi | unitless | (B3−B11)/(B3+B11), Sentinel-2 SR Harmonized; green 10 m and SWIR 20 m native. |
| built_probability | 0–1 | Dynamic World built-class probability, 10 m native. |
| tree_probability | 0–1 | Dynamic World tree-class probability, 10 m native. |
| crop_probability | 0–1 | Dynamic World crop-class probability, 10 m native. |
| dist_centre_m | m | Nearest geometry of the OSM Yalova city place node. |
| dist_road_m | m | Nearest OSM motorway, trunk, primary or secondary road including links. |
| dist_transit_m | m | Nearest mapped bus stop, platform, stop position, bus/ferry terminal, rail station or halt. |
| dist_school_m | m | Nearest OSM amenity=school geometry. |
| dist_hospital_m | m | Nearest OSM amenity=hospital or healthcare=hospital. |
| dist_park_m | m | Nearest OSM leisure=park. |
| dist_coast_m | m | Nearest OSM natural=coastline. |

The GEE script uses 25 October through 23 November 2026 inclusive, computes per-pixel temporal medians and exports 30 m pixels in EPSG:32635. The backend averages valid cell centres inside a 100 m radius. Missing values remain missing in the analytical file and are imputed using only each model-training fold. Dynamic World probabilities are continuous scores. The separate 9 November Copernicus reference layer uses 60 m cells and three indices; its file does not enter model training.

OSM source epoch is 22 November 2026 at 21:20:48 UTC. Vector geometry has variable positional accuracy and lacks a fixed pixel resolution. All distances use nearest geometry in the terrestrial province plus its 18 km external buffer. Feature uploads have their own source and date manifests. Full original tag specifications and source links are in `layers/vector_sources.json`.

## Outputs and diagnostic fields

| Column | Unit / definition |
|---|---|
| pred_tl_m2 | Prediction in TL/m², floored at zero for display. Registered listings use the winning family's model that held out their block, including their fair-price and scenario checks. Unlisted locations and grids use the final full-cohort model. |
| price_index | 100 × predicted unit price / median of the baseline province-wide grid predictions. A zoning-specific scenario keeps this baseline denominator. |
| value_class | Lower below 75, Middle from 75 to below 125, Upper from 125 index points. |
| gap_pct | 100 × (asking unit price / predicted unit price − 1). Undefined if prediction is zero. Negative indicates a lower asking price. |
| nearest_listing_m | Distance between a grid evaluation point and the nearest training listing in metres. |
| environment_missing | At least one environmental input was missing at a grid evaluation point. |
| local_i, p_local, cluster | Local Moran statistic, two-sided conditional permutation pseudo-p and quadrant label. |
| block_5km, outer_fold | Projected 5 km block key and held-out fold. |
| observed | Observed asking TL/m² in the held-out prediction table. Three named model columns contain their out-of-fold predictions. |
| feature, mean_abs_shap_tl_m2 | Transformed feature name and average absolute SHAP contribution in TL/m² across a seeded sample of up to 80 listings. |
| longitude, latitude (grid CSV) | Point on the land-clipped cell, used to evaluate local predictors. Grid GeoJSON geometry is the clipped cell. |

The public data export is restricted to longitude, latitude, price_tl, area_m2, imar_durumu and ad_date. The private GPKG and regression CSV retain full attributes. The generated SHP field-alias dictionary resolves the DBF ten-character field-name limit.

