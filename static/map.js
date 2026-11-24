'use strict';
const $=id=>document.getElementById(id);
if(location.hostname==='127.0.0.1' && location.hash.startsWith('#session=')){
 const key=new URLSearchParams(location.hash.slice(1)).get('session');
 history.replaceState(null,'',location.pathname+location.search);
 if(key)$('admin').value=key;
}
const fmt=(v,dp=0)=>Number(v).toLocaleString('en-GB',{maximumFractionDigits:dp});
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const map=L.map('map',{minZoom:7,maxZoom:19}).setView([40.615,29.22],10);
map.attributionControl.setPrefix(false);
map.attributionControl.addAttribution('© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>');
L.control.scale({imperial:false}).addTo(map);
const territory=L.layerGroup().addTo(map), overlays=L.layerGroup().addTo(map), markers=L.layerGroup().addTo(map);
const classes={Lower:'#6ca4a0',Middle:'#e7bd77',Upper:'#ad543f'};
const clusters={'High–high':'#b53643','Low–low':'#356bb1','High–low':'#e99893','Low–high':'#94c9e1','Not significant':'#c5c9c5'};
const names={centre:'City centre',road:'Main road',transit:'Public transport',school:'School',hospital:'Hospital',park:'Park',coast:'Coast'};
let state,points=[],cells=[],lisa=[],roads,boundary,selected=null,pin=null,renderToken=0,zoneCache=new Map(),estimateToken=0;
const pilotGrids=new Map();
let verifiedPilot;
const portal=async(url,opts)=>{const res=await fetch(url,opts);const data=await res.json();if(!res.ok)throw new Error(data.error||'The server could not complete the request.');return data;};
const line=(title,value)=>'<div><b>'+esc(title)+'</b> '+esc(value)+'</div>';
function legend(colors,labels){$('legend').innerHTML=Object.entries(colors).map(([key,val])=>'<span class="legend-chip"><i class="swatch" style="background:'+val+'"></i>'+esc(labels?.[key]||key)+'</span>').join('');}
function pick(lat,lon,record=null){
 selected=record;
 const form=$('estimate');
 for(const [k,v] of Object.entries({latitude:lat.toFixed(7),longitude:lon.toFixed(7),area_m2:record?.area_m2||'',imar_durumu:record?.imar_durumu||'',asking_tl:record?.price_tl||'',emsal:'',scenario_emsal:''}))form.elements[k].value=v;
 if(pin)map.removeLayer(pin);
 pin=L.circleMarker([lat,lon],{radius:8,color:'#102c2b',weight:3,fillColor:'#fffff0',fillOpacity:1}).addTo(map);
 inspect();
}
async function inspect(){
 const token=++estimateToken,$out=$('result'),val=Object.fromEntries(new FormData($('estimate')));
 if(selected && Math.abs(selected.latitude-Number(val.latitude))<1e-6 && Math.abs(selected.longitude-Number(val.longitude))<1e-6) val.record_key=selected.record_key;
 try{
 const data=await portal('/api/estimate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(val)});
 if(token!==estimateToken)return;
 let h='<h3>'+esc(val.record_key||'Selected location')+'</h3><p>'+esc(val.latitude)+'° N · '+esc(val.longitude)+'° E</p>';
 if(data.available){
 if(data.mode==='pilot')h+='<p class="notice">Exploratory model comparison. The small sample and high spatial error limit parcel-level interpretation.</p>';
 h+='<p class="stat">'+fmt(data.pred_tl_m2)+' TL/m²</p><div class="kv">'+line('Estimated total',fmt(data.total_tl)+' TL')+line('Index',fmt(data.price_index,1))+line('Zoning',data.profile.imar_durumu)+line('Area',fmt(data.profile.area_m2)+' m²')+line('Floor-area ratio',data.profile.emsal??'Unknown')+line('Maximum height',data.profile.gabari_m??'Unknown')+line('Deed type',data.profile.tapu_durumu)+'</div>';
 if(selected&&val.record_key)h+='<p>'+line('Listing date',selected.ad_date)+line('Asking price',fmt(selected.price_tl)+' TL')+'</p>';
 if(data.verdict)h+='<p><b>'+esc(data.verdict)+'</b> · asking price differs by '+fmt(data.gap_pct,1)+'% from the estimate. Fair range ±15%.</p>';
 if('scenario_tl_m2' in data)h+='<p>Scenario estimate <b>'+fmt(data.scenario_tl_m2)+' TL/m²</b> · change '+fmt(data.scenario_change_tl_m2)+' TL/m².</p>';
 if(data.missing_environment)h+='<p>Some satellite inputs were missing and were imputed by the model.</p>';
 }else {h+='<p class="notice">No trained valuation is available for this location.</p>';
 if(Object.keys(data.reference_indices||{}).length)h+='<p>Copernicus reference · 9 Nov 2026 · 100 m buffer</p><div class="kv">'+Object.entries(data.reference_indices).map(([k,v])=>line(k.toUpperCase(),v??'No clear pixels')).join('')+'</div>';}
 h+='<div class="kv">'+Object.entries(data.distances).map(([k,v])=>line(names[k],fmt(v)+' m')).join('')+'</div>';$out.innerHTML=h;
 }catch(e){if(token===estimateToken)$out.textContent=e.message;}
}
map.on('click',e=>pick(e.latlng.lat,e.latlng.lng));
$('estimate').onsubmit=e=>{e.preventDefault();inspect();};
async function draw(){
 const token=++renderToken,mode=$('mapMode').value,zone=$('zoning').value,clas=$('vclass').value;
 territory.eachLayer(layer=>{if(layer.setStyle)layer.setStyle({fillOpacity:mode==='rgb'?0:.88});});
 overlays.clearLayers();markers.clearLayers();$('legend').textContent='';
 let caption=state.model?'Choose a location to inspect the reference parcel.':'No verified listing model is active. Click land to inspect measured accessibility.';
 if(mode==='rgb'&&state.rgb){const info=state.rgb;L.imageOverlay('/static/yalova_rgb.jpg',info.bounds,{opacity:.95}).addTo(overlays);caption='Sentinel-2 optical image · '+info.date+' · '+info.credit;}
 if(mode==='rgb'&&!state.rgb)caption='A satellite preview has not been installed.';
 if(mode==='pilot'||mode==='pilotCentres'){
  const verified=mode==='pilotCentres';
  if(!pilotGrids.has(mode))pilotGrids.set(mode,await portal(verified?'/static/verified_pilot.geojson':'/static/november_pilot.geojson'));
  if(token!==renderToken)return;
  const color=index=>index<75?classes.Lower:index<125?classes.Middle:classes.Upper;
  L.geoJSON(pilotGrids.get(mode),{style:f=>({weight:.3,color:color(f.properties.index_100),fillColor:color(f.properties.index_100),fillOpacity:.82}),
   onEachFeature:(f,layer)=>{
    const p=f.properties;
    layer.options.bubblingMouseEvents=false;
    layer.bindPopup((verified?'<b>Verified parcel centres</b>':'<b>November research pilot</b>')+line('Reference parcel',fmt(p.pilot_tl_m2)+' TL/m²')+
      line('Price index',fmt(p.index_100,1))+line('Nearest sample',fmt(p.distance_to_sample_m)+' m')+
      line('Sample coverage',p.inside_sample_hull?'Inside sample footprint':'Beyond sample footprint'));
   }}).addTo(overlays);
  legend(classes,{Lower:'Index below 75',Middle:'75 to <125',Upper:'125 and above'});
  caption=verified?verifiedPilot.caption:'November 2026 research pilot · Click a cell. Index 100 represents the grid median for a 774 m² residential reference parcel. Based on 22 dated map pins. Spatial test R² = −0.150.';
 }
 if(['price','index'].includes(mode)){
 let features=cells;
 if(zone&&state.model){if(!zoneCache.has(zone))zoneCache.set(zone,await portal('/api/surface?zoning='+encodeURIComponent(zone)));if(token!==renderToken)return;features=zoneCache.get(zone).features;}
 const median=state.model?.grid_median_tl_m2||0;
 L.geoJSON(features.filter(f=>!clas||f.properties.value_class===clas),{interactive:false,style:f=>({weight:.15,color:classes[f.properties.value_class],fillColor:classes[f.properties.value_class],fillOpacity:.75})}).addTo(overlays);
 if(state.model)legend(classes,mode==='index'?{Lower:'Below 75',Middle:'75 to <125',Upper:'125 and above'}:{Lower:'Below '+fmt(.75*median),Middle:fmt(.75*median)+' to <'+fmt(1.25*median),Upper:fmt(1.25*median)+' TL/m² and above'});
 caption=state.model?'500 m clipped cells · baseline study-area median = 100 · '+(zone||'reference zoning')+'.':'The land-value surface requires a completed training run.';}
 if(mode==='lisa'){L.geoJSON(lisa,{pointToLayer:(f,ll)=>L.circleMarker(ll,{radius:4,weight:1,color:'#425850',fillOpacity:.9,fillColor:clusters[f.properties.cluster]})}).addTo(overlays);
 if(state.model)legend(clusters);caption=state.model?'Eight nearest neighbours · local conditional permutation p ≤ 0.05, unadjusted.':'Cluster tests require observed listing prices.';}
 if(mode==='context'&&roads)L.geoJSON(roads,{interactive:false,style:{color:'#9f8161',weight:1.3,opacity:.8}}).addTo(overlays);
 const max=$('budget').value,min=$('minArea').value,hi=$('maxArea').value;
 const sorted=points.filter(p=>(!max||p.price_tl<=+max)&&(!min||p.area_m2>=+min)&&(!hi||p.area_m2<=+hi)&&(!zone||p.imar_durumu===zone)&&(!clas||p.value_class===clas)).sort((a,b)=>a.gap_pct-b.gap_pct);
 $('listingCount').textContent='Matching listings · '+sorted.length;$('listingList').replaceChildren();
 if(!sorted.length)$('listingList').textContent=points.length?'No listings match these filters.':'The collection ledger has no trained listings yet.';
 sorted.forEach((p,i)=>{
 const select=()=>{map.setView([p.latitude,p.longitude],Math.max(map.getZoom(),13));pick(p.latitude,p.longitude,p);};
 if(mode!=='lisa')L.circleMarker([p.latitude,p.longitude],{radius:i===0?6:4,color:'#274f43',fillColor:i===0?'#ffe596':'#fff',fillOpacity:.95,weight:2,bubblingMouseEvents:false}).on('click',select).addTo(markers);
 if(i<50){const b=document.createElement('button');b.className='listing-btn';b.textContent=p.record_key+' · '+fmt(p.price_tl)+' TL · '+fmt(p.gap_pct,1)+'%';b.onclick=select;$('listingList').append(b);}
 });$('mapCaption').textContent=caption;
}
function renderModel(){
 const m=state.model,old=state.previous;
 if(!m){
  $('modelBody').innerHTML='<h3>November spatial pilot</h3><p>Twenty-two dated offers in three districts were tested across five spatial folds. Price errors are measured in TL/m².</p><table><tr><th>Model</th><th>RMSE</th><th>R²</th></tr><tr><td>LightGBM</td><td>6,331</td><td>−0.150</td></tr><tr><td>Random Forest</td><td>6,891</td><td>−0.362</td></tr><tr><td>XGBoost</td><td>7,250</td><td>−0.507</td></tr></table><p>The pilot map holds the reference parcel fixed across the province. The limited sample and high prediction error make individual price advice unreliable.</p><p class="notice">The production model awaits parcel-centre verification and the Earth Engine raster.</p>';
  const scores=verifiedPilot.scores.map(s=>'<tr><td>'+esc(s.model)+'</td><td>'+fmt(s.rmse)+'</td><td>'+fmt(s.r2,3)+'</td></tr>').join('');
  $('modelBody').insertAdjacentHTML('afterbegin','<h3>Verified parcel centres</h3><p>'+esc(verifiedPilot.summary)+'</p><table><tr><th>Model</th><th>RMSE</th><th>R²</th></tr>'+scores+'</table>');
  $('downloads').innerHTML='<a href="/static/verified_pilot.geojson" download>Verified-centre pilot grid (GeoJSON)</a><br><a href="/static/november_pilot.geojson" download>Advertising-pin pilot grid (GeoJSON)</a>';
  return;
 }
 const body=m.models.map(row=>'<tr><td>'+esc(row.model)+'</td><td>'+fmt(row.rmse)+'</td><td>'+fmt(row.r2,3)+'</td></tr>').join('');
 let html='<p><b>'+esc(m.mode==='pilot'?'Active research pilot':'Active project model')+'</b><br>Version '+esc(m.version)+'<br>'+esc(m.trained_utc)+'<br>'+fmt(m.n)+' listings · '+esc(m.period.join(' – '))+'</p><table><tr><th>Model</th><th>RMSE (TL/m²)</th><th>R²</th></tr>'+body+'</table>';
 if(old)html+='<p>Previous version '+esc(old.version)+': '+esc(old.winner)+' · RMSE '+fmt(old.models[0].rmse)+' TL/m² · R² '+fmt(old.models[0].r2,3)+'. Comparisons use each version’s cohort.</p>';
 html+='<h3>Spatial dependence</h3><p>Global Moran’s I '+fmt(m.moran.i,3)+' · p '+fmt(m.moran.p,3)+'</p><h3>Mean absolute SHAP (TL/m²)</h3>'+m.top_shap.map(r=>line(r.feature,fmt(r.mean_abs_shap_tl_m2))).join('');
 $('modelBody').innerHTML=html;$('downloads').innerHTML=Object.entries({grid:'Valuation grid CSV',map:'Valuation grid GeoJSON',listings:'Listing estimates CSV',lisa:'LISA clusters GeoJSON',accuracy:'Metrics and version JSON',shap:'SHAP summary CSV'}).map(([key,title])=>'<a href="/api/download/'+key+'">'+title+'</a>').join('');
}
async function refresh(initial=false){
 [state,boundary,roads,verifiedPilot]=await Promise.all([portal('/api/status'),portal('/api/map/boundary'),portal('/api/map/road'),portal('/static/verified_pilot.json')]);
 const [pts,grid,cl]=await Promise.all(['listings','grid','lisa'].map(k=>portal('/api/map/'+k)));
 points=pts.features.map(f=>f.properties);cells=grid.features;lisa=cl.features;zoneCache.clear();territory.clearLayers();
 const outline=L.geoJSON(boundary,{interactive:false,style:{color:'#48725e',weight:1.6,fillColor:'#c9d9be',fillOpacity:.9}}).addTo(territory);
 if(initial&&outline.getBounds().isValid())map.fitBounds(outline.getBounds(),{padding:[9,9]});
 const zones=[...new Set(points.map(p=>p.imar_durumu))].sort();$('zoning').innerHTML='<option value="">All zoning</option>';$('zoningList').replaceChildren();
 for(const z of zones){$('zoning').add(new Option(z,z));$('zoningList').append(new Option(z,z));}
 $('count').textContent=state.ledger_count+' / 300 listings with verified coordinates recorded.'+(state.missing_layers.length?' Missing local inputs: '+state.missing_layers.join(', ')+'.':' Local feature layers installed.');
 renderModel();await draw();
}
for(const id of ['mapMode','zoning','vclass','budget','minArea','maxArea'])$(id).addEventListener('input',()=>draw().catch(e=>$('mapCaption').textContent=e.message));
for(const b of document.querySelectorAll('.tab'))b.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));document.querySelectorAll('.tabcontent').forEach(x=>x.hidden=x.id!==b.dataset.tab);};
$('uploadType').onchange=()=>$('featureOpts').hidden=$('uploadType').value!=='features';
const manualFields={ilan_no:'Listing number',ad_date:'Date posted',url:'Source URL',collected_on:'Date collected',latitude:'Latitude',longitude:'Longitude',imar_durumu:'Zoning',area_m2:'Parcel area (m²)',price_tl:'Total asking price (TL)',emsal:'Floor-area ratio',gabari_m:'Maximum height (m)',tapu_durumu:'Deed status',kimden:'Seller category'};
for(const [key,label] of Object.entries(manualFields)){
 const l=document.createElement('label');l.textContent=label;const i=document.createElement(key==='kimden'?'select':'input');i.name=key;i.required=!['emsal','gabari_m','tapu_durumu','kimden'].includes(key);
 if(key==='kimden')for(const s of ['Unknown','Owner','Agency','Developer','Bank','Public institution','Other'])i.add(new Option(s,s));
 if(['ad_date','collected_on'].includes(key))i.type='date';if(key==='url')i.type='url';if(['latitude','longitude','area_m2','price_tl','emsal','gabari_m'].includes(key)){i.type='number';i.step='any';}l.append(i);$('manual').append(l);
}
$('manual').insertAdjacentHTML('beforeend','<label>Coordinate verification<select name="coordinate_basis"><option>Parcel centroid on listing map</option><option>Verified cadastral parcel centroid</option></select></label><button class="action">Save verified listing</button>');
async function change(button,fn){
 button.disabled=true;$('message').textContent='Processing…';
 try{const result=await fn();$('message').textContent=result.message;await refresh();}
 catch(e){$('message').textContent=e.message;}
 finally{button.disabled=false;}
}
const adminHeaders=()=>({'X-Admin-Token':$('admin').value});
$('referenceDownload').onclick=async e=>{
 const button=e.currentTarget;button.disabled=true;
 try{
  const response=await fetch('/api/private/references',{headers:adminHeaders()});
  if(!response.ok)throw new Error((await response.json()).error);
  const url=URL.createObjectURL(await response.blob());
  const link=document.createElement('a');link.href=url;link.download='listing_reference_register.csv';link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  $('message').textContent='Downloaded the private reference register.';
 }catch(error){$('message').textContent=error.message;}
 finally{button.disabled=false;}
};
$('manual').onsubmit=e=>{e.preventDefault();const form=e.currentTarget;
 change(e.submitter,async()=>{const row=Object.fromEntries(new FormData(form));const col=Object.keys(row);const csv=col.join(',')+'\n'+col.map(k=>'"'+row[k].replaceAll('"','""')+'"').join(',')+'\n';const fd=new FormData();fd.set('file',new Blob([csv]),'entry.csv');const r=await portal('/api/upload/listings',{method:'POST',headers:adminHeaders(),body:fd});form.reset();return r;});};
$('upload').onsubmit=e=>{e.preventDefault();change(e.submitter,()=>portal('/api/upload/'+$('uploadType').value,{method:'POST',headers:adminHeaders(),body:new FormData($('upload'))}));};
$('train').onclick=e=>change(e.currentTarget,()=>portal('/api/retrain',{method:'POST',headers:adminHeaders()}));
$('pilotTrain').onclick=e=>change(e.currentTarget,()=>portal('/api/retrain/pilot',{method:'POST',headers:adminHeaders()}));
refresh(true).catch(e=>{$('mapCaption').textContent=e.message;});

