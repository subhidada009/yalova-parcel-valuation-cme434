"""Generate a private report appendix and a strictly allowlisted public CSV."""
from argparse import ArgumentParser
import json
from pathlib import Path
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Patch

TITLE="A GIS and ML-Based Land Parcel Valuation System for Decision Support"
TEAM="SUBHI YASER SUBHI DDA · 2310213583       Magd Shalaby · 2210213583"
SUP="Supervisor: Dr. Öğr. Üyesi Sohaib K. M. Abujayyab"
FIELDS=["longitude","latitude","price_tl","area_m2","imar_durumu","ad_date"]


def build(state,out):
    marker=json.loads((state/"active.json").read_text())
    version=state/"versions"/marker["version"]
    metrics=json.loads((version/"metrics.json").read_text())
    data=pd.read_csv(version/"regression_dataset.csv",dtype={"ilan_no":"string"})
    private=out/"release_private";private.mkdir(parents=True,exist_ok=True)
    public=out/"release_public";public.mkdir(parents=True,exist_ok=True)
    data[FIELDS].to_csv(public/"model_inputs.csv",index=False)
    data[["record_key","ilan_no","url","ad_date","collected_on","coordinate_basis"]].to_csv(private/"private_report_appendix.csv",index=False)
    with PdfPages(private/"valuation_results.pdf") as pdf:
        def page():
            fig,ax=plt.subplots(figsize=(11.69,8.27))
            fig.text(.055,.95,"YALOVA  /  PARCEL VALUATION",color="#27624d",weight="bold")
            fig.text(.055,.065,TEAM+"\n"+SUP,fontsize=9)
            fig.subplots_adjust(top=.86,bottom=.16,left=.09,right=.92)
            return fig,ax
        fig,ax=page();ax.axis("off")
        ax.text(0,.98,TITLE,fontsize=15,weight="bold",wrap=True,transform=ax.transAxes)
        text=["Model results  ·  "+metrics["version"],"Training date  "+metrics["trained_utc"],
              f"{metrics['n']} listings  |  collection  {' to '.join(metrics['period'])}",
              "Pooled out-of-block accuracy"]
        text += [f"{m['model']}     RMSE {m['rmse']:,.0f} TL/m²     R² {m['r2']:.3f}" for m in metrics["models"]]
        text += [f"Lowest RMSE: {metrics['winner']}",f"Global Moran’s I {metrics['moran']['i']:.4f}, permutation p {metrics['moran']['p']:.3f}",
                 f"Study-area grid median {metrics['grid_median_tl_m2']:,.0f} TL/m² · {metrics['grid_cells']:,} cells",
                 f"Grid cells with at least one missing environmental band: {metrics['grid_missing_environment']}",
                 "Public links and the archive DOI should accompany the final report."]
        ax.text(0,.87,"\n\n".join(text),transform=ax.transAxes,va="top",fontsize=11)
        pdf.savefig(fig);plt.close(fig)
        fig,ax=page()
        cells=gpd.read_file(version/"grid.geojson").to_crs(32635)
        cells.plot(ax=ax,column="price_index",legend=True,cmap="viridis",linewidth=0,
                   legend_kwds={"label":"Reference-parcel price index · study-area median = 100","shrink":.7})
        ax.set_title("Predicted land price index on the 500 m grid");ax.set_axis_off();pdf.savefig(fig);plt.close(fig)
        fig,ax=page()
        cells.plot(ax=ax,column="pred_tl_m2",legend=True,cmap="cividis",linewidth=0,
                   legend_kwds={"label":"Predicted asking price (TL/m²)","shrink":.7})
        ax.set_title("Reference-parcel predicted unit value");ax.set_axis_off();pdf.savefig(fig);plt.close(fig)
        fig,ax=page()
        lisa=gpd.read_file(version/"lisa.geojson").to_crs(32635)
        boundary=gpd.read_file(version/"layers"/"boundary.geojson").to_crs(32635)
        boundary.boundary.plot(ax=ax,linewidth=.6,color="#577261")
        colors={"High–high":"#b53643","Low–low":"#356bb1","High–low":"#e99893","Low–high":"#94c9e1","Not significant":"#c5c9c5"}
        lisa.plot(ax=ax,color=lisa.cluster.map(colors),markersize=15)
        ax.legend(handles=[Patch(color=c,label=k) for k,c in colors.items()],loc="lower right",fontsize=8)
        ax.set_title("Local Moran clusters · eight nearest neighbours · unadjusted p ≤ 0.05")
        ax.set_axis_off();pdf.savefig(fig);plt.close(fig)
        fig,ax=page()
        shap=pd.read_csv(version/"shap_summary.csv").head(12).iloc[::-1]
        ax.barh(shap.feature.str.replace("numeric__","").str.replace("classes__",""),shap.mean_abs_shap_tl_m2,color="#397963")
        fig.subplots_adjust(left=.29);ax.set_xlabel("Mean absolute SHAP value (TL/m²)");ax.set_title("Leading features of the selected model")
        pdf.savefig(fig);plt.close(fig)

if __name__=="__main__":
    cli=ArgumentParser(description=__doc__)
    cli.add_argument("state",type=Path);cli.add_argument("output",type=Path)
    a=cli.parse_args();build(a.state,a.output)

