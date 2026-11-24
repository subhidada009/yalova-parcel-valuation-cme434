# A GIS and ML-Based Land Parcel Valuation System for Decision Support

**Yalova Province, Türkiye**  
CME434 Geographic Information Systems, Department of Computer Engineering, Karabük University

| Group member | Student number |
|---|---|
| SUBHI YASER SUBHI DDA | 2310213583 |
| Magd Shalaby | 2210213583 |

Supervisor: Dr. Öğr. Üyesi Sohaib K. M. Abujayyab

## Status on 24 November 2026

The private register contains 300 distinct land-sale references checked in Brave on 24 November 2026. Fifty-seven have an evidenced original publication date, 30 were published from 24 September to 24 November 2026, and 33 match cadastral centroids. Three references meet the original-date and single-centroid checks together. The full study still needs a cohort of 300 verified parcels and the six-band provincial Earth Engine raster.

[Live Python valuation application](https://yalova-parcel-valuation-cme434.onrender.com) · [Earlier Yalova atlas](https://subhidada009.github.io/yalova-parcel-valuation-cme434/) · [Source repository](https://github.com/subhidada009/yalova-parcel-valuation-cme434) · [Latest research release](https://github.com/subhidada009/yalova-parcel-valuation-cme434/releases/latest)

[![DOI](https://zenodo.org/badge/DOI/10.5281%2Fzenodo.24491177.svg)](https://doi.org/10.5281/zenodo.24491177)

The current pilot adds 14 previously verified observations to the three qualifying references. It uses 17 dated parcel centres and 15 predictors. With five held-out spatial folds, LightGBM had the lowest RMSE at 6,038 TL/m² and an R² of −0.339. The reviewer package contains the 17-row verified upload, joined GIS points, complete diagnostics and the separate 300-reference register. [TKGM Parcel Sorgu](https://parselsorgu.tkgm.gov.tr/)

## Open the application

The Flask application serves the revised 17-parcel pilot and accepts private data through its administrator interface. The included Render Blueprint uses the free Docker service and temporary storage for uploads. Download private results before restarting that service. The static atlas preserves the earlier 13-parcel experiment.

Choose **Price index** in the Flask app for the revised valuation surface. Click a cell or select a listing to inspect the estimate. Use the Model tab for scores, SHAP, LISA and the 3,401-cell grid downloads.

On Windows, extract the complete folder and double-click **Start_Yalova.cmd**. It creates a Python 3.12 environment, installs dependencies and opens the browser. The terminal prints the local administrator key for the Data tab. First-time dependency installation requires internet access. Leave the terminal open while using the application.

On macOS/Linux, use Python 3.12 and run the following commands from this directory.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python serve.py --desktop
```

Default local address: http://127.0.0.1:8434 . Leaflet, all display layers and all prediction inputs are local. The backend makes no external data requests. An administrator key is needed only for uploads and training. Read-only requests work without a key.

## Geographic inputs

The Earth Engine NDVI export for Armutlu covers six dated cadastral centres. The Sentinel-2 SR window was 25 October to 24 November 2026 with a 20% scene cloud setting. Means over 100 m buffers ranged from 0.583 to 0.804. The downloaded GeoTIFF and its metadata are in the layers directory. Run `python preparation/sample_gee_ndvi.py verified/value_points.gpkg layers/gee_armutlu_ndvi.tif ndvi_means.csv` with the verified points from the private analysis archive to reproduce the six results. The province-wide pilot predictors use the separately documented Copernicus source. [Earth Engine spectral calculator](https://defaniarman.users.earthengine.app/view/s2-spectral-calc)

- Eight WGS84 GeoJSON layers and their licence, snapshot time and extraction rules are in `layers/`. Shipped OSM snapshot: 22 November 2026 at 21:20:48 UTC. The seven accessibility layers cover the terrestrial region and an 18 km margin. To rebuild them, download the pinned national PBF in `layers/vector_sources.json`, install `osmium` and run `python preparation/extract_vectors.py path/to/turkey-261122.osm.pbf layers`. [Geofabrik](https://download.geofabrik.de/europe/turkey.html)
- The Sentinel-2C RGB mosaic and independent 60 m three-band reference come from 9 November 2026. Their STAC product identifiers are in `layers/rgb_bounds.json`. The reference preview can be rebuilt with `python preparation/copernicus_reference.py`. The Earth Engine and Copernicus outputs have different provenance.
- Open `preparation/earth_engine.js` in a registered Earth Engine Code Editor project. Run it, check the RGB granule list, non-zero collection sizes and the dated display, then start all three Drive export tasks. Place the six-band file in `layers/environment.tif` and its inventory in `layers/satellite_inventory.csv`. Keep the dated GEE RGB export as report evidence. Confirm the six band names/order, EPSG:32635, 30 m pixels and NoData −9999. [Earth Engine Code Editor](https://code.earthengine.google.com/)
- To reproduce the 500 m geographic context measurements, run `python preparation/describe_location.py`. Results are in `analysis/`. They describe distance across land, independent of listing availability.

## Record eligible listings

The private reference register can be replaced from **Data → Upload records or a feature layer → Replacement private reference register (CSV)**. The supplied 300-reference CSV includes coordinate quality and date evidence. Its download requires the administrator key. For training, upload `verified_pilot_upload.csv` as **New verified listings for training** and choose **Retrain research pilot** in a fresh state directory.

Start with the province-wide land sale pages on [Hepsiemlak](https://www.hepsiemlak.com/yalova-satilik/arsa) and [Emlakjet](https://www.emlakjet.com/satilik-arsa/yalova). These are human browsing links. Record each selected advertisement's own URL in the private ledger. Keep track of district coverage and confirm whether similarly located offers refer to the same parcel.

Open **Data → Record one manually checked listing**, or download the private listing CSV template from that tab. The spreadsheet header uses ASCII field names. Keep original listing numbers as text. Enter dates as YYYY-MM-DD, metric areas and heights, and total asking prices in TL with no thousands separator. Translate controlled categories consistently into English, retaining the original source privately when needed. Use “Unknown” for an unstated deed or seller category and leave an unreported numeric Emsal or Gabari blank. Seller category is an office/owner category; do not enter a name or contact details.

1. Review each public sale advertisement manually in a normal browser, according to the site's terms. Select a land parcel within Yalova. Exclude apartments, rental offers, fractional prices without a defined share area and duplicates.
2. Read the parcel location from the listing map. Accept a centroid identified on that map or a cadastral centroid checked against it. If the map gives only an approximate neighbourhood, skip it. Record the chosen verification method, source URL, ad number, posting date and collection date.
3. Collect within one short fieldwork window. This configuration validates at most 61 elapsed days across the oldest posting and latest collection. Recheck reposts and cross-site duplicates before submission. Use a current cohort for each study release.
4. Upload CSV or WGS84 GeoJSON Points using the **Data** tab and the administrator key. The application checks dates, required fields, numeric values, URLs, containment and duplicate source references. If any row fails, the upload is rejected as a unit.
5. **Retrain with staged data** after reaching 300 listings and installing the GEE export. Existing label uploads append to the ledger. Keep new cohorts separate if their dates fall outside the specified window. To start a new cohort use a new persistent state directory. A feature upload replaces the entire corresponding vector layer in the next trained version. CSV represents point geometry; roads/coast require GeoJSON lines. Supply the source and snapshot date. New features should retain complete boundary-buffer coverage.

## Analysis and results

For a selected recorded parcel, the application uses the winning-family model that was trained without that parcel's spatial block. This avoids pricing a listing against a fit that has already seen its asking price. An arbitrary map point and the province grid use the model refitted on the entire cohort.

The pipeline computes 18 features, nested spatial cross-validation of three tuned models, Moran's I, conditional LISA, SHAP and a province-wide 500 m prediction grid. See `data_dictionary.md` and `notebooks/valuation.ipynb`. A new version is activated after the entire rebuild succeeds. The Data and Model tabs show progress inputs, versions and comparable metrics. Filtering by zoning recalculates the grid with the selected zoning category. The scenario changes a parcel's floor-area ratio while holding the other inputs fixed.

A successful build writes `private_state/versions/<version>/`: `value_points.csv`, `value_points.geojson`, `value_points.gpkg`, the SHP sidecars, `regression_dataset.csv`, `held_out_predictions.csv`, `metrics.json`, `lisa.geojson`, `shap_summary.csv`, grid CSV/GeoJSON, and the fitted model. Private GIS exports include source identifiers. The GPKG/CSV preserve full text; SHP uses DBF field aliases in `shapefile_fields.json` and has a 254-byte text limit.

To create the private report appendix, a results supplement with figures, and the strictly limited public data export, run:

```bash
python preparation/release_outputs.py private_state release_build
```

Only `release_build/release_public/model_inputs.csv` is intended for a public source repository or archive. It includes coordinates, price, area, zoning and posting date. Keep `release_private`, complete GIS tables, uploaded labels, ad IDs, source URLs, administrator keys and private version directories outside public Git and Zenodo. Contributors can reproduce the full pipeline with their own manually collected private fields; the disclosure-minimised public CSV alone cannot recreate all private attributes.

## Reproducing a public release

1. Create a public GitHub repository under the group's account. Each student commits the work they actually contributed under their own identity. Include the source, notebook, requirements, permitted layers and appropriate download instructions.
2. Deploy the included Dockerfile on a Python-capable host with sufficient RAM and persistent disk. Mount a persistent directory at `/data/yalova`, set `YALOVA_STATE` to that directory, and set `YALOVA_ADMIN_TOKEN` using the host's secret store. After an initial clone add the genuine GEE export in `layers/` before building the host image. Transfer the completed private state securely to the mounted directory, or upload and train there. Confirm the public URL survives a restart and performs predictions from stored layers.
3. Enable the repository in Zenodo's GitHub integration, confirm both creators’ names and their surname order, and preserve the supervisor line from `.zenodo.json`. Publish a tagged GitHub release, check the resulting public Zenodo record and copy the issued DOI badge into this README. [Zenodo guide](https://help.zenodo.org/docs/github/)
4. Add the verified public repository, hosted URL and DOI to this README and the English report. Include the GEE image, real model table, LISA/SHAP/valuation maps and findings in the final report, with the listing reference appendix submitted privately.

## Attribution

Original software is MIT-licensed. OSM-derived geography is © OpenStreetMap contributors and distributed under ODbL 1.0. The optical imagery contains modified Copernicus Sentinel data (2026). Dynamic World estimates require attribution to Google and the World Resources Institute under CC BY 4.0. Leaflet retains its bundled BSD licence. [OSM](https://www.openstreetmap.org/copyright) · [Dynamic World](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1)

Results are guidance only. An official appraisal requires a licensed valuation expert.

