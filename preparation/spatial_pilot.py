"""Build a private, provisional spatial dataset from direct listing pages.

Usage: python preparation/spatial_pilot.py ../Yalova_Direct_Listings.csv pilot
"""
import argparse
import json
from pathlib import Path
import sys

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from sklearn.metrics import mean_squared_error, r2_score
from scipy.spatial import cKDTree

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
import engine

def measure_locations(points, layers):
    for name, geometries in layers.vectors.items():
        pairs, distance = geometries.sindex.nearest(points.geometry, return_all=False, return_distance=True)
        values = np.full(len(points), np.nan)
        values[pairs[0]] = distance
        assert np.isfinite(values).all() and (values >= 0).all()
        points["dist_" + name + "_m"] = values
    with rasterio.open(PROJECT / "layers/copernicus_indices_reference.tif") as src:
        assert src.crs == points.crs and list(src.descriptions) == ["ndvi", "ndbi", "mndwi"]
        bands = list(src.descriptions)
        points[bands] = [engine.mean_bands(src, g.buffer(engine.RADIUS_M)) for g in points.geometry]
    return bands

def build(source, out, cadastral=False):
    out.mkdir(exist_ok=True, parents=True)
    ledger = pd.read_csv(source, dtype={"listing_id": str, "block_no": str, "parcel_no": str})
    selected = ledger.centroid_verified.eq("Yes") if cadastral else ledger.pin_inside_yalova.eq("Yes")
    mapped = ledger.loc[selected].copy()
    mapped["ilan_no"] = mapped["listing_id"]
    mapped["record_key"] = mapped.source + "/" + mapped.listing_id
    assert mapped.record_key.is_unique
    points = engine.geoframe(mapped).reset_index(drop=True)
    layers = engine.LocalLayers(PROJECT / "layers")
    assert points.geometry.covered_by(layers.boundary).all()
    points["x"], points["y"] = points.geometry.x, points.geometry.y
    points["unit_tl_m2"] = points.asking_price_tl / points.area_m2
    bands = measure_locations(points, layers)
    points["imar_durumu"] = points.zoning.fillna("Unspecified")
    points["tapu_durumu"] = points.deed_type.fillna("Unspecified")
    for raw, name in [("far_as_listed", "emsal"), ("height_as_listed_m", "gabari_m")]:
        numbers = pd.to_numeric(points[raw].astype("string").str.replace(",", ".", regex=False), errors="coerce")
        valid = numbers.gt(0)
        if name == "emsal":
            valid &= ~points.review_note.fillna("").str.contains("ambiguous floor area ratio", case=False)
        points[name] = numbers.where(valid)
    predictors = engine.ADS + bands + engine.DIST
    assert len(predictors) == 15
    points["pilot_model_row"] = points.ad_date.notna() & points.evidence_group.eq("Published")
    training = points.loc[points.pilot_model_row].copy().reset_index(drop=True)
    assert pd.to_datetime(training.ad_date).between("2026-09-24", "2026-11-24").all()
    # Time-uncertain listings contribute geometry to the inventory only.
    assert training[predictors].notna().any().all()
    points.drop(columns="geometry").to_csv(out / "regression_dataset.csv", index=False)
    points.drop(columns="geometry").to_csv(out / "value_points.csv", index=False)
    points.to_file(out / "value_points.gpkg", layer="value_points", driver="GPKG")
    points.to_crs(4326).to_file(out / "value_points.geojson", driver="GeoJSON")
    long_fields=[col for col in points.columns if col!="geometry" and len(col)>10]
    aliases={name:f"field_{i:03d}" for i,name in enumerate(long_fields,1)}
    shape=points.rename(columns=aliases).copy()
    for col in shape.columns:
        if col == "geometry" or not pd.api.types.is_string_dtype(shape[col].dtype):
            continue
        shape[col]=shape[col].map(lambda v: v.encode("utf8")[:254].decode("utf8","ignore") if isinstance(v,str) else v)
    shape.to_file(out / "value_points.shp", encoding="UTF-8")
    (out/"shapefile_fields.json").write_text(json.dumps({aliases.get(n,n):n for n in points.columns if n!="geometry"},indent=2),encoding="utf8")
    model, metrics, folds, params, predictions, _ = engine.comparison(training, predictors)
    for fold in predictions.outer_fold.unique():
        held = predictions.outer_fold.eq(fold)
        other = predictions.loc[~held]
        assert set(predictions.loc[held, "block_5km"]).isdisjoint(other.block_5km)
        predictions.loc[held, "Training median"] = other.observed.median()
    naive = predictions["Training median"]
    metrics.append({"model":"Training median", "rmse":float(np.sqrt(mean_squared_error(predictions.observed, naive))),
                    "r2":float(r2_score(predictions.observed, naive))})
    results = pd.DataFrame(metrics)
    results.to_csv(out / "model_comparison.csv", index=False)
    predictions.to_csv(out / "held_out_predictions.csv", index=False)
    pd.DataFrame(folds).to_json(out / "spatial_folds.json", orient="records", indent=2)
    # Only one publication-dated row per advertised point is admitted to Moran's weights.
    assert not training[["x","y"]].duplicated().any()
    spatial, lisa = engine.moran(training)
    lisa.to_crs(4326).to_file(out / "local_moran.geojson", driver="GeoJSON")
    importance = engine.shap_summary(model, training, predictors)
    importance.to_csv(out / "shap_summary.csv", index=False)
    grid=engine.grid_points(layers)
    centres=engine.geoframe(grid.drop(columns="geometry"))
    measure_locations(centres,layers)
    reference={}
    for col in engine.ADS:
        reference[col]=str(training[col].mode()[0]) if col in engine.CATS else float(training[col].median())
        centres[col]=reference[col]
    grid["pilot_tl_m2"]=model.predict(centres[predictors])
    grid_median=float(grid.pilot_tl_m2.median())
    assert grid_median>0 and np.isfinite(grid.pilot_tl_m2).all()
    grid["index_100"]=100*grid.pilot_tl_m2/grid_median
    grid["inside_sample_hull"]=centres.geometry.covered_by(training.geometry.union_all().convex_hull)
    grid["distance_to_sample_m"]=cKDTree(training[["x","y"]]).query(np.column_stack([centres.geometry.x,centres.geometry.y]))[0]
    grid["valid_spectral_observation"]=centres[bands].notna().all(axis=1)
    grid.to_crs(4326).to_file(out/"exploratory_grid.geojson",driver="GeoJSON")
    grid.drop(columns="geometry").to_csv(out/"exploratory_grid.csv",index=False)
    fig,ax=plt.subplots(figsize=(10.4,4.5))
    grid.plot(ax=ax,column="index_100",cmap="viridis",edgecolor="none",legend=True,legend_kwds={"label":"Pilot index (province grid median = 100)","shrink":.72})
    border=gpd.GeoSeries([training.geometry.union_all().convex_hull],crs=points.crs)
    border.boundary.plot(ax=ax,color="#e35c32",linewidth=1.4,linestyle="--")
    training.plot(ax=ax,markersize=9,color="#fefefe",edgecolor="#333333",linewidth=.4)
    ax.set_axis_off();ax.set_title("Reference-parcel estimates on a 500 m grid",loc="left",fontweight="bold")
    fig.text(.05,.06,"Dots mark model observations. The dashed outline encloses their locations. Values beyond it are extrapolations.",fontsize=9)
    fig.savefig(out/"exploratory_index.png",dpi=150,bbox_inches="tight");plt.close(fig)
    manifest = dict(ledger_rows=len(ledger),mapped=len(points),publication_dated_mapped=len(training),
                    coordinate_source="TKGM parcel polygon centroid" if cadastral else "Advertising map pin",
                    spatial_blocks=int(predictions.block_5km.nunique()),districts=training.district.value_counts().to_dict(),
                    mapped_complete_spectral=int(points[bands].notna().all(axis=1).sum()),
                    training_complete_spectral=int(training[bands].notna().all(axis=1).sum()),
                    actual_predictors=predictors,best_ml=metrics[0]["model"],best_parameters=params,
                    spatial_autocorrelation=spatial,grid_cells=len(grid),grid_cells_inside_sample_hull=int(grid.inside_sample_hull.sum()),
                    grid_reference=reference,grid_median_tl_m2=grid_median)
    (out / "results.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf8")
    fig,axes=plt.subplots(2,1,figsize=(10.4,7.2),gridspec_kw={"height_ratios":[2,1.1]})
    ax=axes[0]
    gpd.GeoSeries([layers.boundary],crs=points.crs).plot(ax=ax,color="#ecf2ee",edgecolor="#6c847b",linewidth=.7)
    points[~points.pilot_model_row].plot(ax=ax,color="#9aa7a2",markersize=11,label="Other direct listings",alpha=.75)
    training.plot(ax=ax,color="#00706b",edgecolor="white",linewidth=.5,markersize=42,label="Publication-dated model sample")
    ax.legend(loc="upper left",frameon=False,fontsize=9)
    ax.set_title("Verified parcel centroids in Yalova" if cadastral else "Advertised land locations in Yalova",loc="left",fontweight="bold",fontsize=15);ax.set_axis_off()
    ax=axes[1];palette=["#08766d"]*3+["#87979e"]
    ax.barh(results.model,results.rmse,color=palette,height=.63);ax.invert_yaxis()
    for i,n in enumerate(results.rmse):ax.text(n,i,f"  {n:,.0f}",va="center",fontsize=9)
    ax.set_xlim(0,results.rmse.max()*1.2);ax.set_xlabel("Held-out RMSE (TL/m²)")
    ax.spines[["top","right"]].set_visible(False)
    ax.set_title(f"Five spatial folds across {manifest['spatial_blocks']} blocks",loc="left",fontweight="bold")
    fig.tight_layout(pad=1.6);fig.savefig(out/"pilot_results.png",dpi=155);plt.close(fig)
    assert len(gpd.read_file(out/"value_points.gpkg"))==len(points)==len(pd.read_csv(out/"regression_dataset.csv"))
    assert len(gpd.read_file(out/"value_points.shp"))==len(points)
    print(json.dumps({k:v for k,v in manifest.items() if k not in ("actual_predictors","best_parameters")},ensure_ascii=False))
    print(results.to_string(index=False))

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("listings",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--cadastral",action="store_true",help="Use the centroid-verified ledger and its polygon-derived coordinates.")
    args=parser.parse_args()
    build(args.listings,args.output,args.cadastral)
