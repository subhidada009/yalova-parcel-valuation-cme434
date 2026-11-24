"""Private collection ledger. No requests are made to listing websites."""
import hashlib
import io
import json
from datetime import date
from urllib.parse import urlsplit

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, shape
from engine import read_layer, geoframe

COLUMNS = ["ilan_no","ad_date","url","collected_on","latitude","longitude","imar_durumu",
           "area_m2","price_tl","emsal","gabari_m","tapu_durumu","kimden","coordinate_basis"]
BASIS = ["Parcel centroid on listing map","Verified cadastral parcel centroid"]
SELLERS = ["Owner","Agency","Developer","Bank","Public institution","Other","Unknown"]
NUMERIC = ["latitude","longitude","area_m2","price_tl","emsal","gabari_m"]


def parse_upload(contents, name, spatial_features=False):
    suffix = name.rsplit(".",1)[-1].lower()
    if suffix == "csv":
        data = pd.read_csv(io.BytesIO(contents), dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if spatial_features:
            for field in ("longitude","latitude"):
                if field not in data:
                    raise ValueError(f"Missing CSV column: {field}.")
            lon=pd.to_numeric(data.longitude,errors="raise")
            lat=pd.to_numeric(data.latitude,errors="raise")
            return gpd.GeoDataFrame(data,geometry=gpd.points_from_xy(lon,lat),crs=4326)
        return data
    if suffix not in ("geojson","json"):
        raise ValueError("Choose a UTF-8 CSV or WGS84 GeoJSON FeatureCollection.")
    obj=json.loads(contents.decode("utf-8-sig"))
    if not isinstance(obj,dict) or obj.get("type")!="FeatureCollection" or not isinstance(obj.get("features"),list) or not obj["features"]:
        raise ValueError("Expected a nonempty WGS84 FeatureCollection.")
    records=[]
    for i,feature in enumerate(obj["features"],1):
        geom=shape(feature["geometry"])
        props=dict(feature.get("properties") or {})
        if geom.is_empty or not geom.is_valid:
            raise ValueError(f"Feature {i} has invalid geometry.")
        if spatial_features:
            props["geometry"]=geom
        else:
            if not isinstance(geom, Point):
                raise ValueError(f"Listing feature {i} must be a Point.")
            for key,val in (("longitude",geom.x),("latitude",geom.y)):
                if key in props and abs(float(props[key])-val)>1e-7:
                    raise ValueError(f"Conflicting {key} in feature {i}.")
                props[key]=val
        records.append(props)
    return gpd.GeoDataFrame(records,crs=4326) if spatial_features else pd.DataFrame(records)


def validate(data, folder, asof=None):
    missing=set(COLUMNS)-set(data.columns)
    if missing:
        raise ValueError("Missing columns: " + ", ".join(sorted(missing)))
    if len(data)==0:
        raise ValueError("The upload has headers but no listings.")
    extras=set(data)-set(COLUMNS)-{"record_key"}
    if extras:
        raise ValueError("Unexpected columns: " + ", ".join(sorted(extras)) + ". Use the private template.")
    result=data[COLUMNS].copy().reset_index(drop=True)
    today=pd.Timestamp(asof or date.today())
    for f in COLUMNS:
        result[f]=result[f].astype("string").str.strip().replace("",pd.NA)
    required=set(COLUMNS)-{"emsal","gabari_m","tapu_durumu","kimden"}
    for f in required:
        bad=result[f].isna()
        if bad.any():
            raise ValueError(f"Row {bad.idxmax()+2}: {f} is required.")
    for f in NUMERIC:
        values=pd.to_numeric(result[f],errors="coerce")
        bad=(result[f].notna() & values.isna()) | np.isinf(values.fillna(0).astype(float))
        if bad.any():
            raise ValueError(f"Row {bad.idxmax()+2}: {f} must be finite and numeric; use a decimal point.")
        result[f]=values.astype(float)
    for f in ["price_tl","area_m2"]:
        if (result[f]<=0).any():
            raise ValueError(f"{f} must be greater than zero.")
    if (result[["emsal","gabari_m"]]<0).any().any():
        raise ValueError("Floor-area ratio and building height cannot be negative.")
    for f in ["ad_date","collected_on"]:
        dates=pd.to_datetime(result[f],format="%Y-%m-%d",errors="coerce")
        if dates.isna().any() or (dates>today).any():
            raise ValueError(f"{f} must use YYYY-MM-DD and cannot be in the future.")
        result[f]=dates
    if (result.ad_date>result.collected_on).any():
        raise ValueError("An advertisement cannot post after its collection date.")
    if (result.collected_on.max()-result.ad_date.min()).days>61:
        raise ValueError("The combined posting and collection window exceeds 61 elapsed days.")
    if not result.coordinate_basis.isin(BASIS).all():
        raise ValueError("Use a verified parcel centroid. Neighbourhood pins are insufficient.")
    if not result.url.map(lambda u: urlsplit(u).scheme in ("http","https") and bool(urlsplit(u).hostname)).all():
        raise ValueError("Each listing needs an absolute public web URL.")
    identity=result.url.map(lambda u:urlsplit(u).hostname.lower().removeprefix("www."))+"|"+result.ilan_no
    if identity.duplicated().any() or result.url.duplicated().any():
        raise ValueError("The file contains a repeated listing reference.")
    if result.duplicated(["longitude","latitude","area_m2"]).any():
        raise ValueError("Review a possible relisting with the same location and parcel area.")
    if not result.longitude.between(-180,180).all() or not result.latitude.between(-90,90).all():
        raise ValueError("Coordinates must be WGS84 longitude and latitude in decimal degrees.")
    boundary=read_layer(folder,"boundary").geometry.union_all()
    inside=geoframe(result).geometry.covered_by(boundary)
    if not inside.all():
        raise ValueError(f"Row {(~inside).idxmax()+2}: point outside the Yalova land boundary.")
    for f in ["ad_date","collected_on"]:
        result[f]=result[f].dt.strftime("%Y-%m-%d")
    for f in ["tapu_durumu","kimden"]:
        result[f]=result[f].fillna("Unknown")
    if not result.kimden.isin(SELLERS).all():
        raise ValueError("Seller category must be Owner, Agency, Developer, Bank, Public institution, Other or Unknown.")
    result["record_key"]=["Y-"+hashlib.sha256(v.encode()).hexdigest()[:12] for v in identity]
    return result

