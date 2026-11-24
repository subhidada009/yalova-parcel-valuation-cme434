"""Describe measured geographic context without using any price labels."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
import numpy as np
import geopandas as gpd
from engine import LocalLayers, grid_points, geoframe, PLACES, GRID_M
ROOT=Path(__file__).resolve().parents[1]
layer=LocalLayers(ROOT/"layers")
grid=grid_points(layer)
pts=geoframe(grid.drop(columns='geometry'))
source={"count":len(grid),"grid_spacing_m":GRID_M,"area_km2":grid.area.sum()/1e6,"distance_summary_m":{}}
folder=ROOT/"analysis"
folder.mkdir(exist_ok=True)
for name in PLACES:
    pair,dist=layer.vectors[name].sindex.nearest(pts.geometry,return_distance=True,return_all=False)
    values=np.empty(len(grid));values[pair[0]]=dist
    grid[name]=values
    source["distance_summary_m"][name]={k:round(float(np.quantile(values,q)),1) for k,q in [('p10',.1),('median',.5),('p90',.9)]}
(folder/"geographic_context.json").write_text(json.dumps(source,indent=2))
grid.drop(columns="geometry").to_csv(folder/"geographic_context.csv",index=False)
colors=['#d9efe8','#9acfc1','#53a598','#357b79','#224e59']
bins=[0,1000,3000,6000,10000,1e9]
fig,ax=plt.subplots(figsize=(11,4.25),facecolor='#f8faf8');ax.set_facecolor('#f8faf8')
grid.plot(column="coast",ax=ax,cmap=ListedColormap(colors),norm=BoundaryNorm(bins,len(colors)),linewidth=0)
gpd.GeoSeries([layer.boundary],crs=32635).boundary.plot(ax=ax,color='#294e49',linewidth=.45)
ax.set_axis_off();ax.set_aspect('equal')
legend=[Patch(facecolor=c,label=l) for c,l in zip(colors,['<1 km','1–3 km','3–6 km','6–10 km','≥10 km'])]
fig.legend(handles=legend,loc='lower center',ncol=5,frameon=False,fontsize=10)
fig.subplots_adjust(left=.025,right=.975,top=.99,bottom=.14)
fig.savefig(folder/"coastal_distance.png",dpi=150,bbox_inches='tight',pad_inches=.07)
print(json.dumps(source,indent=1))

