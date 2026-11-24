"""Export a portable fitted model, aggregate surfaces and anonymised point results."""
import argparse
import json
from pathlib import Path
import shutil

import pandas as pd

def export(version, target):
    metrics=json.loads((version/"metrics.json").read_text(encoding="utf8"))
    if metrics.get("mode")!="pilot":
        raise ValueError("Select a completed pilot model version.")
    target.mkdir(parents=True,exist_ok=True)
    allowed=["metrics.json","model.joblib","held_out_models.joblib","grid.csv","grid.geojson",
             "grid_inputs.csv","lisa.geojson","shap_summary.csv"]
    for name in allowed:
        shutil.copyfile(version/name,target/name)
    fields=["record_key","ad_date","longitude","latitude","price_tl","area_m2","imar_durumu",
            "unit_tl_m2","pred_tl_m2","price_index","value_class","gap_pct"]
    points=pd.read_csv(version/"listings.csv")[fields]
    folds=pd.read_csv(version/"regression_dataset.csv",usecols=["record_key","outer_fold"])
    points.merge(folds,on="record_key",validate="one_to_one").to_csv(target/"listings.csv",index=False)
    assert points.record_key.str.fullmatch(r"Y-[a-f0-9]{12}").all()
    assert set(p.name for p in target.iterdir())==set(allowed+["listings.csv"])

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version",type=Path)
    parser.add_argument("target",type=Path)
    args=parser.parse_args()
    export(args.version,args.target)
