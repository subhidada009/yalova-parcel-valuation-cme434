# A GIS and ML-Based Land Parcel Valuation System for Decision Support

**Yalova Province, Türkiye**  
CME434 Geographic Information Systems, Department of Computer Engineering, Karabük University

| Group member | Student number |
|---|---|
| SUBHI YASER SUBHI DDA | 2310213583 |
| Magd Shalaby | 2210213583 |

Supervisor: Dr. Öğr. Üyesi Sohaib K. M. Abujayyab

## Status on 24 November 2026

The private ledger contains 113 land offers with asking prices and areas verified through direct listing pages in Brave on 23–24 November 2026. It includes 28 original publication dates in the review window, 10 dated source updates and 75 undated offers. The 106 in-boundary advertising pins are provisional parcel locations. The full study still needs a cohort of 300 verified parcels and the six-band provincial Earth Engine raster.

[Interactive Yalova atlas](https://subhidada009.github.io/yalova-parcel-valuation-cme434/) · [Source repository](https://github.com/subhidada009/yalova-parcel-valuation-cme434) · [Tagged release](https://github.com/subhidada009/yalova-parcel-valuation-cme434/releases/tag/v1.0.0)

[![DOI](https://zenodo.org/badge/1469693624.svg)](https://zenodo.org/badge/latestdoi/1469693624)

The private spatial pilot joins 15 predictors to those 106 positions. Its model sample includes 22 original publication-dated offers in three districts and eleven 5 km spatial blocks. Across five held-out folds, LightGBM achieved RMSE of 6,331 TL/m² and R² of −0.150. The private archive contains the model comparison, SHAP, spatial autocorrelation results and an exploratory 500 m index grid. From this directory, run `python preparation/spatial_pilot.py PATH_TO/Yalova_Direct_Listings.csv PATH_TO/pilot` to reproduce it. The application retains its separate production training workflow.

Among 57 cadastral lookups, 44 offers matched the location, block, parcel number and registered area. The public TKGM viewer supplied the parcel polygons. Forty-two of these offers also provided a map pin. The median pin-to-centroid distance was 176 m. Thirteen of the 44 offers had original posting dates inside the study window. The independent model at these verified centres ranked Random Forest first, with RMSE of 6,964 TL/m² and R² of −0.521. The private archive includes the checked polygons, reproducible verification and modelling commands, and a validated 13-row application upload. [TKGM Parcel Sorgu](https://parselsorgu.tkgm.gov.tr/)

## Open the application

The hosted atlas displays the 3,401-cell exploratory price surface, held-out estimates and floor-area scenarios for 13 dated and cadastral-verified offers. The Flask application also serves a bundled trained model and accepts private data through its administrator interface. The included Render Blueprint uses the free Docker service and temporary storage for uploads. Download private results before restarting that service.

Choose **Verified parcel centres · price index** for the analysis based on cadastral polygons, or **November pilot · price index** for the analysis based on advertising pins. Click a cell for the reference value, index and nearest-sample distance. The Model tab shows both sets of test scores. Each downloadable pilot grid contains 3,401 cells.

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

The Earth Engine NDVI export for Armutlu covers six dated cadastral centres. The Sentinel-2 SR window was 25 October to 24 November 2026 with a 20% scene cloud setting. Means over 100 m buffers ranged from 0.583 to 0.804. The downloaded GeoTIFF and its metadata are in the layers directory. The province-wide pilot predictors use the separately documented Copernicus source. [Earth Engine spectral calculator](https://defaniarman.users.earthengine.app/view/s2-spectral-calc)

- Eight WGS84 GeoJSON layers and their licence, snapshot time and extraction rules are in `layers/`. Shipped OSM snapshot: 22 November 2026 at 21:20:48 UTC. The seven accessibility layers cover the terrestrial region and an 18 km margin. To rebuild them, download the pinned national PBF in `layers/vector_sources.json`, install `osmium` and run `python preparation/extract_vectors.py path/to/turkey-261122.osm.pbf layers`. [Geofabrik](https://download.geofabrik.de/europe/turkey.html)
- The Sentinel-2C RGB mosaic and independent 60 m three-band reference come from 9 November 2026. Their STAC product identifiers are in `layers/rgb_bounds.json`. The reference preview can be rebuilt with `python preparation/copernicus_reference.py`. The Earth Engine and Copernicus outputs have different provenance.
- Open `preparation/earth_engine.js` in a registered Earth Engine Code Editor project. Run it, check the RGB granule list, non-zero collection sizes and the dated display, then start all three Drive export tasks. Place the six-band file in `layers/environment.tif` and its inventory in `layers/satellite_inventory.csv`. Keep the dated GEE RGB export as report evidence. Confirm the six band names/order, EPSG:32635, 30 m pixels and NoData −9999. [Earth Engine Code Editor](https://code.earthengine.google.com/)
- To reproduce the 500 m geographic context measurements, run `python preparation/describe_location.py`. Results are in `analysis/`. They describe distance across land, independent of listing availability.

## Record eligible listings

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

