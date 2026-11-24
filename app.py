"""Yalova parcel valuation web GIS. The served application uses local files only."""
from contextlib import contextmanager
from datetime import datetime, timezone, date
from functools import lru_cache, wraps
import hmac
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import threading
import uuid

from flask import Flask, abort, jsonify, render_template, request, send_file
from filelock import FileLock, Timeout
import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import Point
from shapely.ops import unary_union
from werkzeug.exceptions import HTTPException

from engine import ADS, BANDS, CATS, DIST, FEATURES, PLACES, LocalLayers, dump, geoframe, read_layer, train, mean_bands, RADIUS_M
from records import COLUMNS, REFERENCE_COLUMNS, parse_upload, validate, validate_references

ROOT=Path(__file__).resolve().parent
BASE=ROOT/"layers"
PUBLIC_PILOT=ROOT/"public_model"
STATE=Path(os.environ.get("YALOVA_STATE",ROOT/"private_state")).resolve()
REFERENCE_REGISTER=STATE/"listing_reference_register.csv"
STATE.mkdir(parents=True,exist_ok=True)
app=Flask(__name__)
app.config["MAX_CONTENT_LENGTH"]=30*1024*1024


def read(path,default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def atomic(path,content):
    tmp=path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    tmp.write_text(content,encoding="utf-8")
    os.replace(tmp,path)


def active():
    marker=read(STATE/"active.json",{})
    if marker:
        return STATE/"versions"/marker["version"]
    return PUBLIC_PILOT if (PUBLIC_PILOT/"metrics.json").is_file() else None


def sources():
    v=active()
    return v/"layers" if v and v!=PUBLIC_PILOT else BASE


def raw():
    path=STATE/"ledger.csv"
    return pd.read_csv(path,dtype=str,keep_default_na=False) if path.exists() else pd.DataFrame(columns=COLUMNS)


def admin(fn):
    @wraps(fn)
    def check(*a,**k):
        secret=os.environ.get("YALOVA_ADMIN_TOKEN","")
        if not secret or not hmac.compare_digest(request.headers.get("X-Admin-Token",""),secret):
            abort(403,description="Enter the project administrator key to change data.")
        return fn(*a,**k)
    return check


@app.errorhandler(HTTPException)
def http_error(exc):
    return jsonify(error=exc.description),exc.code


@app.errorhandler(ValueError)
@app.errorhandler(TypeError)
@app.errorhandler(KeyError)
def invalid(exc):
    return jsonify(error=str(exc)),400


@app.errorhandler(Timeout)
def busy(exc):
    return jsonify(error="Another update is running. Try again after it finishes."),409


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/status")
def status():
    v=active()
    metric=read(v/"metrics.json") if v else None
    prior=read(v/"previous.json") if v else None
    layers=sources()
    needed=["boundary.geojson",*(n+".geojson" for n in PLACES),"environment.tif"]
    return jsonify(model=metric,previous=prior,missing_layers=[n for n in needed if not (layers/n).exists()],
                   ledger_count=len(raw()),rgb=read(BASE/"rgb_bounds.json"),vectors=read(BASE/"vector_sources.json"))


@app.get("/api/template/<kind>")
def template(kind):
    columns={"features":["longitude","latitude"],"listings":COLUMNS,"references":REFERENCE_COLUMNS}
    if kind not in columns:
        abort(404)
    return send_file(io.BytesIO((",".join(columns[kind])+"\n").encode()),mimetype="text/csv",
                     as_attachment=True,download_name=kind+"_template.csv")


@app.get("/api/private/references")
@admin
def reference_register():
    if not REFERENCE_REGISTER.is_file():
        abort(404,description="No private reference register has been uploaded.")
    response=send_file(REFERENCE_REGISTER,as_attachment=True)
    response.cache_control.private=True
    response.cache_control.no_store=True
    return response


@app.get("/api/map/<name>")
def map_data(name):
    v=active()
    if name in ["grid","lisa","listings"]:
        if not v:
            return jsonify(type="FeatureCollection",features=[])
        if name=="listings":
            df=pd.read_csv(v/"listings.csv")
            return app.response_class(geoframe(df).to_crs(4326).to_json(drop_id=True),mimetype="application/json")
        return send_file(v/(name+".geojson"))
    if name not in ["boundary","road","centre"]:
        abort(404)
    path=sources()/(name+".geojson")
    if not path.exists():
        return jsonify(type="FeatureCollection",features=[])
    return app.response_class(display_geometry(str(path)),mimetype="application/json")


@lru_cache(maxsize=24)
def display_geometry(path):
    layer=gpd.read_file(path).to_crs(32635)[["geometry"]]
    layer.geometry=layer.simplify(45,preserve_topology=True)
    return layer.to_crs(4326).to_json(drop_id=True)


@app.get("/api/download/<name>")
def download(name):
    files={"grid":"grid.csv","listings":"listings.csv","lisa":"lisa.geojson","accuracy":"metrics.json","shap":"shap_summary.csv","map":"grid.geojson"}
    v=active()
    if not v or name not in files:
        abort(404,description="This result is available after a completed training run.")
    return send_file(v/files[name],as_attachment=True)


@app.get("/api/surface")
def surface():
    v=active()
    if not v:
        return jsonify(type="FeatureCollection",features=[])
    name=request.args.get("zoning","")
    listings=pd.read_csv(v/"listings.csv")
    if name not in set(listings.imar_durumu):
        raise ValueError("Choose an observed zoning category.")
    frame=pd.read_csv(v/"grid_inputs.csv")
    frame["imar_durumu"]=name
    _,model=loaded(str(v))
    cells=gpd.read_file(v/"grid.geojson")
    columns=read(v/"metrics.json").get("features",FEATURES)
    cells["pred_tl_m2"]=np.maximum(model.predict(frame[columns]),0)
    cells["price_index"]=100*cells.pred_tl_m2/read(v/"metrics.json")["grid_median_tl_m2"]
    cells["value_class"]=np.select([cells.price_index<75,cells.price_index<125],["Lower","Middle"],default="Upper")
    return app.response_class(cells.to_json(drop_id=True),mimetype="application/json")


@lru_cache(maxsize=2)
def loaded(path):
    v=Path(path)
    folder=BASE if v==PUBLIC_PILOT else v/"layers"
    return LocalLayers(folder,pilot=read(v/"metrics.json").get("mode")=="pilot"),joblib.load(v/"model.joblib")


@lru_cache(maxsize=2)
def fold_models(path):
    return joblib.load(Path(path)/"held_out_models.joblib")


def positive(payload,key,allow_zero=False):
    val=float(payload[key])
    if not np.isfinite(val) or (val<0 if allow_zero else val<=0):
        raise ValueError(key+" is outside its allowed range.")
    return val


@app.post("/api/estimate")
def estimate():
    v=active()
    val=request.get_json()
    lon,lat=float(val["longitude"]),float(val["latitude"])
    if not np.isfinite([lon,lat]).all() or not (-180<=lon<=180 and -90<=lat<=90):
        raise ValueError("Enter valid longitude and latitude.")
    point=pd.DataFrame([{"longitude":lon,"latitude":lat}])
    geo=geoframe(point).geometry.iloc[0]
    path=sources()
    if not (path/"boundary.geojson").exists() or not read_layer(path,"boundary").geometry.union_all().covers(geo):
        raise ValueError("Select a point on land inside Yalova Province.")
    if not v:
        distances={n:round(read_layer(path,n).distance(geo).min()) for n in PLACES if (path/(n+".geojson")).exists()}
        indices={}
        reference=BASE/"copernicus_indices_reference.tif"
        if reference.exists():
            with rasterio.open(reference) as src:
                values=mean_bands(src,geo.buffer(RADIUS_M))
                indices={key:round(v,3) if np.isfinite(v) else None for key,v in zip(BANDS[:3],values)}
        return jsonify(available=False,distances=distances,reference_indices=indices)
    layers,model=loaded(str(v))
    metrics=read(v/"metrics.json")
    profile=metrics["reference_parcel"].copy()
    held_out_anchor=None
    if val.get("record_key"):
        ledger=pd.read_csv(v/("listings.csv" if v==PUBLIC_PILOT else "regression_dataset.csv"))
        matched=ledger[ledger.record_key==val["record_key"]]
        if matched.empty:
            raise ValueError("Listing unavailable in this model version.")
        profile.update(matched.iloc[0][[k for k in ADS if k in matched]].to_dict())
        if v==PUBLIC_PILOT:
            held_out_anchor=(float(matched.iloc[0].pred_tl_m2),profile.copy())
        model=fold_models(str(v))[int(matched.iloc[0].outer_fold)]
        if abs(lon-matched.iloc[0].longitude)>1e-6 or abs(lat-matched.iloc[0].latitude)>1e-6:
            raise ValueError("The selected listing and coordinates differ.")
    for field in ["area_m2","emsal","gabari_m"]:
        if val.get(field) not in (None,""):
            profile[field]=positive(val,field,allow_zero=field!="area_m2")
    for field in CATS:
        if val.get(field):
            profile[field]=str(val[field])[:100]
    attrs=point.assign(**{k:np.nan if x is None else x for k,x in profile.items()})
    enriched=layers.enrich(attrs)
    adjustment=0.0
    if held_out_anchor:
        original= enriched.copy()
        for k,x in held_out_anchor[1].items():
            original[k]=x
        adjustment=held_out_anchor[0]-float(model.predict(original[layers.features])[0])
    pred=max(0,float(model.predict(enriched[layers.features])[0])+adjustment)
    payload=dict(available=True,pred_tl_m2=pred,total_tl=pred*profile["area_m2"],profile=profile,
                 price_index=100*pred/metrics["grid_median_tl_m2"],missing_environment=enriched[layers.bands].isna().any(axis=1).item(),mode=metrics.get("mode","full"),
                 distances={n:round(float(enriched["dist_"+n+"_m"].iloc[0])) for n in PLACES})
    if val.get("asking_tl") not in ("",None) and payload["total_tl"]>0:
        gap=100*(positive(val,"asking_tl")/payload["total_tl"]-1)
        payload.update(gap_pct=gap,verdict="Underpriced" if gap < -15-1e-9 else "Overpriced" if gap > 15+1e-9 else "Fair")
    if val.get("scenario_emsal") not in ("",None):
        updated=enriched.copy()
        updated["emsal"]=positive(val,"scenario_emsal",True)
        after=max(0,float(model.predict(updated[layers.features])[0])+adjustment)
        payload.update(scenario_tl_m2=after,scenario_change_tl_m2=after-pred)
    payload["profile"]={k:None if pd.isna(v) else v for k,v in profile.items()}
    return jsonify(payload)


@app.post("/api/upload/<kind>")
@admin
def upload(kind):
    if kind not in ("listings","features","references"):
        abort(404)
    item=request.files["file"]
    if kind=="references" and not (item.filename or "").lower().endswith(".csv"):
        raise ValueError("The private reference register must be a CSV file.")
    frame=parse_upload(item.read(),item.filename or "",kind=="features")
    with FileLock(str(STATE/"write.lock"),timeout=0):
        if kind=="references":
            checked=validate_references(frame)
            atomic(REFERENCE_REGISTER,checked.to_csv(index=False))
            return jsonify(message=f"Saved {len(checked)} references privately. The model inputs are unchanged.")
        if kind=="listings":
            checked=validate(pd.concat([raw()[COLUMNS],frame],ignore_index=True),BASE)
            atomic(STATE/"ledger.csv",checked.to_csv(index=False))
            return jsonify(message=f"Accepted {len(frame)} listings. The private ledger now contains {len(checked)}.")
        name=request.form.get("name","")
        if name not in PLACES:
            raise ValueError("Choose one supported vector layer.")
        source=request.form.get("source","").strip()
        when=date.fromisoformat(request.form.get("source_date",""))
        if not source or when>date.today():
            raise ValueError("Supply the source and a valid snapshot date.")
        if frame.empty or frame.crs is None or frame.to_crs(4326).geometry.is_empty.any():
            raise ValueError("The feature layer is empty or invalid.")
        allowed={"centre":{"Point"},"road":{"LineString","MultiLineString"},"coast":{"LineString","MultiLineString"}}
        if not set(frame.geom_type).issubset(allowed.get(name,{"Point","MultiPoint","LineString","MultiLineString","Polygon","MultiPolygon"})):
            raise ValueError("The geometry type is unsuitable for this layer.")
        bx=read_layer(BASE,"boundary").geometry.union_all().buffer(18000)
        proj=frame.to_crs(32635)
        if not proj.geometry.intersects(bx).all():
            raise ValueError("Features must intersect Yalova or its 18 km accessibility margin.")
        folder=STATE/"staged"
        folder.mkdir(exist_ok=True)
        atomic(folder/(name+".geojson"),frame[["geometry"]].to_crs(4326).to_json(drop_id=True))
        atomic(folder/(name+"_source.json"),json.dumps(dict(source=source,date=when.isoformat())))
        return jsonify(message=f"Staged {len(frame)} features as the complete replacement for {name}. Retrain to activate.")


@app.post("/api/retrain",defaults={"pilot":False})
@app.post("/api/retrain/pilot",defaults={"pilot":True})
@admin
def rebuild(pilot):
    with FileLock(str(STATE/"write.lock"),timeout=0):
        frame=validate(raw(),BASE)
        if pilot and len(frame)<9:
            raise ValueError("The pilot requires at least nine observations for its eight-neighbour spatial test.")
        if not pilot and len(frame)<300:
            raise ValueError(f"{len(frame)} verified listings recorded; 300 are required for the project run.")
        prev=active()
        source=sources()
        if not pilot and not (source/"environment.tif").is_file() and not (BASE/"environment.tif").is_file():
            raise ValueError("Place the dated Earth Engine export environment.tif in the local layers directory.")
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:6]
        out=STATE/"versions"/stamp
        out.mkdir(parents=True)
        try:
            shutil.copytree(source,out/"layers",ignore=shutil.ignore_patterns("*.jpg","*.png"))
            for raster in ("environment.tif","copernicus_indices_reference.tif"):
                if (BASE/raster).is_file() and not (out/"layers"/raster).is_file():
                    shutil.copy2(BASE/raster,out/"layers"/raster)
            staged=STATE/"staged"
            if staged.exists():
                for f in staged.iterdir():
                    shutil.copy2(f,out/"layers"/f.name)
            metrics=train(frame,out/"layers",out,pilot=pilot)
            metrics.update(version=stamp,trained_utc=datetime.now(timezone.utc).isoformat())
            dump(out/"metrics.json",metrics)
            dump(out/"previous.json",read(prev/"metrics.json") if prev else None)
            atomic(STATE/"active.json",json.dumps({"version":stamp}))
        except Exception:
            shutil.rmtree(out,ignore_errors=True)
            raise
        return jsonify(message="Model, maps and diagnostics updated.",version=stamp)

