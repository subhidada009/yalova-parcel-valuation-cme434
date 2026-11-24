"""Local feature extraction, spatial validation, model selection and map generation."""
from contextlib import ExitStack
from pathlib import Path
import json
import math

import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import Window, from_bounds
from scipy.spatial import cKDTree
from shapely.geometry import mapping
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor
from lightgbm import LGBMRegressor

CRS = "EPSG:32635"
BANDS = ["ndvi", "ndbi", "mndwi", "built_probability", "tree_probability", "crop_probability"]
PLACES = ["centre", "road", "transit", "school", "hospital", "park", "coast"]
CATS = ["imar_durumu", "tapu_durumu"]
ADS = ["area_m2", "emsal", "gabari_m"] + CATS
DIST = ["dist_" + name + "_m" for name in PLACES]
FEATURES = ADS + BANDS + DIST
SEED = 434
BLOCK_M = 5000
GRID_M = 500
RADIUS_M = 100


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def read_layer(folder, name):
    layer = gpd.read_file(Path(folder) / (name + ".geojson"))
    if layer.empty or layer.crs is None:
        raise ValueError(f"The {name} layer is empty or lacks a CRS.")
    return layer.to_crs(CRS)


def geoframe(data):
    return gpd.GeoDataFrame(data.copy(), geometry=gpd.points_from_xy(data.longitude, data.latitude), crs=4326).to_crs(CRS)


def mean_bands(src, shape):
    raw = from_bounds(*shape.bounds, src.transform)
    left, top = math.floor(raw.col_off), math.floor(raw.row_off)
    window = Window(left, top, math.ceil(raw.col_off + raw.width) - left,
                    math.ceil(raw.row_off + raw.height) - top)
    values = src.read(window=window, masked=True, boundless=True)
    inside = geometry_mask([mapping(shape)], out_shape=values.shape[1:],
                           transform=src.window_transform(window), invert=True)
    return [float(v.compressed().mean()) if v.count() else np.nan
            for v in np.ma.masked_invalid(np.ma.array(values, mask=np.ma.getmaskarray(values) | ~inside))]


class LocalLayers:
    def __init__(self, folder, pilot=False):
        self.folder = Path(folder)
        self.bands = BANDS[:3] if pilot else BANDS
        self.features = ADS + self.bands + DIST
        self.raster = self.folder / ("copernicus_indices_reference.tif" if pilot else "environment.tif")
        self.boundary = read_layer(folder, "boundary").geometry.union_all()
        self.vectors = {name: read_layer(folder, name).geometry for name in PLACES}

    def enrich(self, data):
        frame = geoframe(data)
        if not frame.geometry.covered_by(self.boundary).all():
            raise ValueError("A point falls outside the Yalova study boundary.")
        frame["x"], frame["y"] = frame.geometry.x, frame.geometry.y
        for name, geometries in self.vectors.items():
            pairs, distances = geometries.sindex.nearest(frame.geometry, return_all=False, return_distance=True)
            results = np.full(len(frame), np.nan)
            results[pairs[0]] = distances
            frame["dist_" + name + "_m"] = results
        with ExitStack() as handles:
            src = handles.enter_context(rasterio.open(self.raster))
            if src.crs is None or src.crs.to_epsg() != 32635 or src.count != len(self.bands):
                raise ValueError(f"Expected {len(self.bands)} raster bands in EPSG:32635.")
            if any(src.descriptions) and list(src.descriptions) != self.bands:
                raise ValueError("The environmental raster band names do not match this analysis.")
            stats = [mean_bands(src, point.buffer(RADIUS_M)) for point in frame.geometry]
        frame[self.bands] = np.asarray(stats)
        return frame


def comparison(data, feature_columns=None):
    feature_columns = FEATURES if feature_columns is None else feature_columns
    numeric = [name for name in feature_columns if name not in CATS]
    enc = ColumnTransformer([
        ("numeric", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), numeric),
        ("classes", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATS)])
    models = {
        "Random Forest": (RandomForestRegressor(n_estimators=160, n_jobs=2, random_state=SEED),
                          {"model__min_samples_leaf": [2, 5], "model__max_features": [0.7, 1.0]}),
        "XGBoost": (XGBRegressor(n_estimators=150, learning_rate=0.055, n_jobs=2, random_state=SEED),
                    {"model__max_depth": [2, 4], "model__subsample": [0.8, 1.0]}),
        "LightGBM": (LGBMRegressor(n_estimators=150, learning_rate=0.055, verbosity=-1,
                                   n_jobs=2, random_state=SEED),
                     {"model__num_leaves": [7, 15], "model__min_child_samples": [2, 4, 8] if len(data)<16 else [8, 20]})}
    x, y = data[feature_columns], data.unit_tl_m2
    blocks = (np.floor(data.x / BLOCK_M).astype(int).astype(str) + "_" +
              np.floor(data.y / BLOCK_M).astype(int).astype(str))
    if blocks.nunique() < 5:
        raise ValueError("Five distinct 5 km spatial blocks are needed for the five outer folds.")
    if y.nunique() < 2:
        raise ValueError("Validation requires variation in observed asking prices per square metre.")
    outer = list(GroupKFold(5).split(x, y, groups=blocks))
    comparisons, folds, predictions, fitted_folds = [], [], {}, {}
    for name, (regressor, grid) in models.items():
        estimator = Pipeline([("encode", enc), ("model", regressor)])
        predictions[name] = np.zeros(len(data))
        fitted_folds[name] = {}
        for fold, (train, test) in enumerate(outer, 1):
            inner = GroupKFold(min(3, blocks.iloc[train].nunique()))
            search = GridSearchCV(estimator, grid, cv=inner, scoring="neg_root_mean_squared_error", error_score="raise")
            search.fit(x.iloc[train], y.iloc[train], groups=blocks.iloc[train])
            fitted_folds[name][fold] = search.best_estimator_
            values = search.predict(x.iloc[test])
            predictions[name][test] = values
            folds.append(dict(model=name, fold=fold, n_test=len(test), blocks=blocks.iloc[test].nunique(),
                              rmse=float(np.sqrt(mean_squared_error(y.iloc[test], values))),
                              r2=float(r2_score(y.iloc[test], values)) if len(test)>1 and y.iloc[test].nunique()>1 else None,
                              parameters=search.best_params_))
        pred = predictions[name]
        comparisons.append(dict(model=name, rmse=float(np.sqrt(mean_squared_error(y, pred))), r2=float(r2_score(y, pred))))
    comparisons.sort(key=lambda row: row["rmse"])
    winner = comparisons[0]["model"]
    model, params = models[winner]
    final = GridSearchCV(Pipeline([("encode", enc), ("model", model)]), params, cv=GroupKFold(5),
                         scoring="neg_root_mean_squared_error", error_score="raise").fit(x, y, groups=blocks)
    diagnostics = pd.DataFrame({"record_key":data.record_key, "block_5km":blocks, "observed":y, **predictions})
    diagnostics["outer_fold"] = 0
    for fold, (_, test) in enumerate(outer, 1):
        diagnostics.iloc[test,diagnostics.columns.get_loc("outer_fold")] = fold
    return final.best_estimator_, comparisons, folds, final.best_params_, diagnostics, fitted_folds[winner]


def moran(frame):
    n = len(frame)
    z = frame.unit_tl_m2.to_numpy(dtype=float)
    z = (z - z.mean()) / z.std()
    tree = cKDTree(frame[["x", "y"]])
    _, near = tree.query(frame[["x", "y"]], k=9)
    neighbors = np.array([row[row != i][:8] for i, row in enumerate(near)])
    lag = z[neighbors].mean(axis=1)
    observed = float(np.mean(z * lag))
    rng = np.random.default_rng(SEED)
    draws = []
    for _ in range(999):
        perm = rng.permutation(z)
        draws.append(float(np.mean(perm * perm[neighbors].mean(axis=1))))
    expected = -1 / (n - 1)
    p_global = (1 + np.count_nonzero(np.abs(np.array(draws) - expected) >= abs(observed - expected))) / 1000
    local_i = z * lag
    p_local = []
    for i in range(n):
        other = np.delete(z, i)
        # Eight different neighbours within each conditional randomisation.
        picks = np.array([rng.choice(n - 1, size=8, replace=False) for _ in range(999)])
        sim = z[i] * other[picks].mean(axis=1)
        centre = z[i] * other.mean()
        p_local.append(float((1 + np.count_nonzero(abs(sim-centre) >= abs(local_i[i]-centre))) / 1000))
    quadrant = np.where(z >= 0, np.where(lag>=0,"High–high","High–low"),np.where(lag>=0,"Low–high","Low–low"))
    labels = np.where(np.array(p_local)<=0.05,quadrant,"Not significant")
    lisa = frame[["record_key","geometry"]].copy().assign(local_i=local_i, p_local=p_local, cluster=labels)
    return {"i":observed, "p":float(p_global), "expected":expected, "permutations":999, "neighbors":8}, lisa


def shap_summary(model, frame, feature_columns=None):
    import shap
    encoder = model.named_steps["encode"]
    actual = frame.sample(min(80,len(frame)),random_state=SEED)
    matrix = np.asarray(encoder.transform(actual[FEATURES if feature_columns is None else feature_columns]))
    reg = model.named_steps["model"]
    try:
        values = shap.TreeExplainer(reg)(matrix, check_additivity=False).values
    except (TypeError, ValueError, RuntimeError):
        mask = shap.maskers.Independent(matrix[:min(32, len(matrix))])
        explain = shap.Explainer(reg.predict, mask, algorithm="permutation", seed=SEED)
        values = explain(matrix, max_evals=2*matrix.shape[1]+1).values
    return pd.DataFrame({"feature":encoder.get_feature_names_out(),
                         "mean_abs_shap_tl_m2":np.abs(values).mean(axis=0)}).sort_values("mean_abs_shap_tl_m2", ascending=False)


def grid_points(layers):
    from shapely import box, point_on_surface, intersection, intersects
    west,south,east,north = layers.boundary.bounds
    xs=np.arange(np.floor(west/GRID_M)*GRID_M,east,GRID_M)
    ys=np.arange(np.floor(south/GRID_M)*GRID_M,north,GRID_M)
    xx,yy=np.meshgrid(xs,ys)
    cells=box(xx.ravel(), yy.ravel(), xx.ravel()+GRID_M, yy.ravel()+GRID_M)
    shapes=intersection(cells[intersects(cells,layers.boundary)],layers.boundary)
    frame=gpd.GeoDataFrame(geometry=shapes,crs=CRS)
    frame=frame[frame.geometry.area>0].reset_index(drop=True)
    centres=gpd.GeoSeries(point_on_surface(frame.geometry),crs=CRS).to_crs(4326)
    frame["longitude"],frame["latitude"]=centres.x,centres.y
    return frame


def value_class(index):
    return np.select([index<75,index<125],["Lower","Middle"],default="Upper")


def train(raw, layer_dir, out, pilot=False):
    out = Path(out)
    layers = LocalLayers(layer_dir, pilot=pilot)
    features=layers.features
    points = layers.enrich(raw)
    if points[layers.bands].isna().all().any():
        raise ValueError("An environmental band has no usable values at any training parcel.")
    points["unit_tl_m2"] = points.price_tl / points.area_m2
    model, scores, folds, best_params, diagnostics, held_out_models = comparison(points,features)
    joblib.dump(held_out_models,out/"held_out_models.joblib")
    diagnostics.to_csv(out/"held_out_predictions.csv",index=False)
    importance=shap_summary(model,points,features)
    importance.to_csv(out/"shap_summary.csv",index=False)
    statistic,lisa=moran(points)
    lisa.to_crs(4326).to_file(out/"lisa.geojson",driver="GeoJSON")
    cells=grid_points(layers)
    profile={col:(str(points[col].mode().iloc[0]) if col in CATS else
                  (float(points[col].median()) if points[col].notna().any() else None)) for col in ADS}
    inputs=cells[["longitude","latitude"]].copy()
    for col,value in profile.items():
        inputs[col]=value if value is not None else np.nan
    grid=layers.enrich(inputs)
    grid[features].to_csv(out/"grid_inputs.csv",index=False)
    cells["pred_tl_m2"]=model.predict(grid[features]).clip(min=0)
    median=float(cells.pred_tl_m2.median())
    if median<=0:
        raise ValueError("The predicted median is not positive.")
    cells["price_index"]=100*cells.pred_tl_m2/median
    cells["value_class"]=value_class(cells.price_index)
    cells["environment_missing"]=grid[layers.bands].isna().any(axis=1)
    cells["nearest_listing_m"]=cKDTree(points[["x","y"]]).query(grid[["x","y"]])[0]
    cells.to_crs(4326).to_file(out/"grid.geojson",driver="GeoJSON")
    cells.drop(columns="geometry").to_csv(out/"grid.csv",index=False)
    points["outer_fold"]=diagnostics["outer_fold"].to_numpy()
    points["pred_tl_m2"]=diagnostics[scores[0]["model"]].to_numpy().clip(min=0)
    points["price_index"]=100*points.pred_tl_m2/median
    points["value_class"]=value_class(points.price_index)
    points["gap_pct"]=100*(points.unit_tl_m2 / points.pred_tl_m2.replace(0,np.nan)-1)
    public_fields=["record_key","ad_date","longitude","latitude","price_tl","area_m2","imar_durumu",
                   "unit_tl_m2","pred_tl_m2","price_index","value_class","gap_pct"]
    points[public_fields].to_csv(out/"listings.csv",index=False)
    points.to_file(out/"value_points.gpkg",layer="value_points",driver="GPKG")
    names={col:col[:10] for col in points.columns}
    names.update({"built_probability":"built_prob","tree_probability":"tree_prob","crop_probability":"crop_prob",
                  "dist_hospital_m":"d_hosp_m","dist_school_m":"d_school_m","dist_transit_m":"d_trans_m"})
    if len(set(names.values())) != len(names) or any(len(n)>10 for n in names.values()):
        raise ValueError("Shapefile field aliases collide.")
    points.rename(columns=names).to_file(out/"value_points.shp",driver="ESRI Shapefile",encoding="UTF-8")
    dump(out/"shapefile_fields.json",names)
    points.to_crs(4326).to_file(out/"value_points.geojson",driver="GeoJSON")
    plain=points.drop(columns="geometry")
    plain.to_csv(out/"regression_dataset.csv",index=False)
    plain.to_csv(out/"value_points.csv",index=False)
    joblib.dump(model,out/"model.joblib")
    return dict(models=scores,folds=folds,parameters=best_params, winner=scores[0]["model"],
                moran=statistic, reference_parcel=profile,grid_median_tl_m2=median,grid_cells=len(grid),
                grid_missing_environment=int(cells.environment_missing.sum()), features=features, mode="pilot" if pilot else "full",
                top_shap=importance.head(8).to_dict("records"),n=len(points),
                period=[str(points.collected_on.min()),str(points.collected_on.max())],
                ad_dates=[str(points.ad_date.min()),str(points.ad_date.max())],
                missing={key:int(points[key].isna().sum()) for key in features})

