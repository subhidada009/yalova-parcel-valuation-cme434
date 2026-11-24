"""Match privately saved TKGM parcel exports to the original land-offer ledger."""
import argparse
import json
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import shape

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
import engine
import records


def run(ledger_path, registry_dir, output):
    output.mkdir(parents=True,exist_ok=True)
    offers=pd.read_csv(ledger_path,dtype={"listing_id":"string","block_no":"string","parcel_no":"string"})
    offers.index=offers.source+"/"+offers.listing_id
    checks=json.loads((registry_dir/"checks.json").read_text(encoding="utf8"))
    verified=[]
    audit=[]
    polygons=[]
    for key,check in checks.items():
        original=offers.loc[key]
        audit.append({"record_key":key,"checked_on":"2026-11-24","status":check["state"],"registry_area_m2":check.get("registry_area_m2"),
                      "advertised_area_m2":original.area_m2,"block_no":original.block_no,"parcel_no":original.parcel_no,
                      "lookup_url":check.get("portalURL"),"review_stage":check.get("phase")})
        if not check.get("file"):
            continue
        item=json.loads((registry_dir/check["file"]).read_text(encoding="utf8"))["features"][0]
        props=item["properties"]
        assert str(props["Ada"])==original.block_no and str(props["ParselNo"])==original.parcel_no
        assert abs(check["registry_area_m2"]-original.area_m2)<=max(1,original.area_m2*.001)
        geom=shape(item["geometry"])
        assert geom.is_valid and geom.geom_type in {"Polygon","MultiPolygon"}
        parcel=gpd.GeoSeries([geom],crs=4326).to_crs(engine.CRS)
        centre=parcel.centroid.iloc[0]
        wgs=gpd.GeoSeries([centre],crs=engine.CRS).to_crs(4326).iloc[0]
        row=original.to_dict()
        separation=np.nan
        if pd.notna(row["longitude"]) and pd.notna(row["latitude"]):
            pin=gpd.GeoSeries(gpd.points_from_xy([row["longitude"]],[row["latitude"]]),crs=4326).to_crs(engine.CRS).iloc[0]
            separation=pin.distance(centre)
        row.update({"advertised_longitude":row["longitude"],"advertised_latitude":row["latitude"],"longitude":wgs.x,"latitude":wgs.y,
                    "centroid_verified":"Yes","registry_area_m2":check["registry_area_m2"],"pin_to_centroid_m":separation,
                    "registry_url":check["portalURL"],"centroid_inside_parcel":geom.covers(wgs)})
        verified.append(row)
        polygons.append({"record_key":key,"registered_m2":check["registry_area_m2"],"geometry":geom})
    pd.DataFrame(audit).to_csv(output/"cadastral_checks.csv",index=False)
    df=pd.DataFrame(verified)
    geoms=gpd.GeoDataFrame(polygons,geometry="geometry",crs=4326)
    geoms.to_file(output/"checked_parcels.geojson",driver="GeoJSON")
    df.to_csv(output/"verified_centroids.csv",index=False)
    dated=df[df.ad_date.notna() & df.evidence_group.eq("Published")].copy()
    assert not dated.duplicated(["district","locality","block_no","parcel_no"]).any()
    # Make an importable private file using only the cohort and the advertised attributes.
    imported=pd.DataFrame({"ilan_no":dated.listing_id,"ad_date":dated.ad_date,"url":dated.url,"collected_on":dated.collected_on,
                           "latitude":dated.latitude,"longitude":dated.longitude,"imar_durumu":dated.zoning,
                           "area_m2":dated.area_m2,"price_tl":dated.asking_price_tl,
                           "emsal":pd.to_numeric(dated.far_as_listed.astype("string").str.replace(",","."),errors="coerce"),
                           "gabari_m":pd.to_numeric(dated.height_as_listed_m.astype("string").str.replace(",","."),errors="coerce"),
                           "tapu_durumu":dated.deed_type,"kimden":dated.seller_type,"coordinate_basis":"Verified cadastral parcel centroid"})
    imported.loc[dated.review_note.fillna("").str.contains("ambiguous floor area ratio",case=False),"emsal"]=np.nan
    imported=imported[imported.imar_durumu.notna()].copy()
    imported.kimden=imported.kimden.map({"Agency":"Agency","Owner":"Owner","Private individual":"Owner","Developer":"Developer","Bank":"Bank","Public institution":"Public institution"}).fillna("Unknown")
    for col in ["emsal","gabari_m"]:
        imported.loc[imported[col]<=0,col]=np.nan
    from datetime import date
    clean=records.validate(imported.astype("string").fillna(""),PROJECT/"layers",asof=date(2026,11,24))
    clean[records.COLUMNS].to_csv(output/"valid_private_upload.csv",index=False)
    summary={"checked":len(audit),"verified":len(df),"dated":len(dated),"import_ready":len(clean),
             "located_source_pins":int(df.pin_to_centroid_m.notna().sum()),"median_offset_m":float(df.pin_to_centroid_m.median()),
             "range_m":[float(df.pin_to_centroid_m.min()),float(df.pin_to_centroid_m.max())],
             "outside_own_footprint":int((~df.centroid_inside_parcel).sum()),"status_counts":pd.DataFrame(audit).status.value_counts().to_dict()}
    (output/"cadastral_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf8")
    print(json.dumps(summary))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger",type=Path)
    parser.add_argument("registry_directory",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    run(args.ledger,args.registry_directory,args.output)
