'use strict';
const byId=id=>document.getElementById(id);
const fmt=(n,d=0)=>Number(n).toLocaleString('en-GB',{maximumFractionDigits:d});
const map=L.map('map',{preferCanvas:true,minZoom:8,maxZoom:18,scrollWheelZoom:false});
map.attributionControl.setPrefix(false);
L.control.scale({imperial:false}).addTo(map);
const surface=L.layerGroup().addTo(map),dots=L.layerGroup().addTo(map);
const bands=['#6aa59a','#ded5a2','#e5ac76','#af695b','#874744'];
const thresholds=[70,95,120,160];
const colour=n=>bands[thresholds.filter(x=>n>=x).length];
const lisaColours={'Not significant':'#777e81','High–high':'#9d3b39','Low–low':'#357b9d','Low–high':'#80b7ce','High–low':'#dd916d'};
let offers=[],grid,province,extent,mode='index',selected;
const esc=value=>String(value).replace(/[&<>"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
function details(entries){return '<dl class="inspect-data">'+entries.map(([label,value])=>'<dt>'+esc(label)+'</dt><dd>'+esc(value)+'</dd>').join('')+'</dl>';}
function showCell(feature){
 const x=feature.properties;
 byId('inspector').innerHTML='<p class="kicker">REFERENCE PARCEL</p><h2>Selected grid cell</h2><p class="price">'+fmt(x.pilot_tl_m2)+' <small>TL/m²</small></p>'+details([['Price index',fmt(x.index_100,1)],['Nearest training parcel',fmt(x.distance_to_sample_m)+' m'],['Sample convex hull',x.inside_sample_hull?'Inside':'Outside']])+'<p class="explain">Estimate for the same 2,340 m² reference field used across the province.</p>';
}
function showOffer(a,zoom){
 selected=a.label;
 if(zoom)map.setView([a.lat,a.lon],Math.max(map.getZoom(),12));
 const expected=a.heldOutRate*a.area,rate=a.askingTL/a.area,gap=100*(rate/a.heldOutRate-1);
 byId('inspector').innerHTML='<p class="kicker">VERIFIED OFFER · '+esc(a.posted)+'</p><h2>'+esc(a.label)+'</h2><p class="price">'+fmt(rate)+' <small>asking TL/m²</small></p>'+details([['Zoning',a.zoning],['Area',fmt(a.area,1)+' m²'],['Asking price',fmt(a.askingTL)+' TL'],['Held-out estimate',fmt(a.heldOutRate)+' TL/m²'],['Estimated total',fmt(expected)+' TL'],['Asking gap',(gap>0?'+':'')+fmt(gap,1)+'%'],['Model comparison',gap< -15?'Underpriced':gap>15?'Overpriced':'Fair'],['LISA',a.cluster]])+'<p class="explain">Held-out error across the sample was 6,964 TL/m². Interpret this comparison as exploratory.</p>';
 if(a.farScenarios){
  const sel=document.createElement('select'),label=document.createElement('label'),out=document.createElement('p');
  label.textContent='Floor-area ratio scenario';label.append(sel);out.className='hint';
  for(const [f] of Object.entries(a.farScenarios))sel.add(new Option(f,f));
  const result=()=>{out.textContent='Scenario estimate: '+fmt(a.farScenarios[sel.value])+' TL/m²';};
  sel.addEventListener('change',result);byId('inspector').append(label,out);result();
 }
 document.querySelectorAll('.listrow').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.id===selected)));
}
function drawOffers(){
 const budget=byId('budget').value,area=byId('area').value,zone=byId('zone').value;
 const subset=offers.filter(a=>(!budget||a.askingTL<=Number(budget))&&(!area||a.area>=Number(area))&&(!zone||a.zoning===zone)).sort((a,b)=>a.askingTL-b.askingTL);
 dots.clearLayers();byId('offer-list').replaceChildren();byId('offer-count').textContent=subset.length;
 for(const a of subset){
  L.circleMarker([a.lat,a.lon],{radius:mode==='lisa'?7:4,weight:1.5,color:'#fff',fillColor:mode==='lisa'?(lisaColours[a.cluster]||'#38564d'):'#183d3b',fillOpacity:1}).on('click',()=>showOffer(a,false)).addTo(dots);
  const button=document.createElement('button');button.type='button';button.className='listrow';button.dataset.id=a.label;button.setAttribute('aria-pressed',String(a.label===selected));
  button.innerHTML='<span><strong>'+esc(a.label)+'</strong><small>'+esc(a.zoning)+' · '+fmt(a.area)+' m²</small></span><span>'+fmt(a.askingTL)+' TL</span>';
  button.onclick=()=>showOffer(a,true);byId('offer-list').append(button);
 }
 if(!subset.length)byId('offer-list').textContent='No offers match these filters.';
}
function draw(){
 surface.clearLayers();let keys=[];
 if(mode==='index'){
  L.geoJSON(grid,{style:f=>({fillColor:colour(f.properties.index_100),fillOpacity:.89,color:colour(f.properties.index_100),weight:.35}),onEachFeature:(f,l)=>l.on('click',()=>showCell(f))}).addTo(surface);
  keys=bands.map((c,i)=>[c,['<70','70–94','95–119','120–159','160+'][i]]);
 } else if(mode==='satellite'){
  L.imageOverlay('assets/yalova_rgb.jpg',[[40.44,28.7],[40.77,29.69]],{opacity:1}).addTo(surface);
 } else {
  keys=[...new Set(offers.map(a=>a.cluster))].map(k=>[lisaColours[k]||'#777',k]);
 }
 L.geoJSON(province,{interactive:false,style:{weight:1.4,color:mode==='satellite'?'#eeebcf':'#4e7166',fillColor:'#d7e3da',fillOpacity:mode==='lisa'?.65:0}}).addTo(surface);
 byId('legend-title').textContent=({'index':'Land price index','satellite':'Sentinel-2C natural colour','lisa':'Local Moran clusters'})[mode];
 byId('legend-unit').textContent=({'index':'Grid median = 100','satellite':'9 November 2026','lisa':'Eight nearest neighbours'})[mode];
 byId('legend-swatches').innerHTML=keys.map(([c,t])=>'<span class="key"><i style="background:'+c+';width:12px;height:12px;display:inline-block"></i>'+esc(t)+'</span>').join(' ');
 byId('caption').textContent=({'index':'Select a grid cell for its estimated unit price and coverage. Dark points mark the 13 verified offers.','satellite':'Copernicus Sentinel-2C · 9 November 2026. Select a dark point for the parcel details.','lisa':'Local significance uses 999 permutations at p ≤ 0.05. Select a point to inspect its cluster.'})[mode];
 document.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===mode)));
 drawOffers();
}
async function start(){
 const get=async p=>{const r=await fetch('assets/'+p);if(!r.ok)throw Error('A local map layer could not load.');return r.json();};
 [grid,province,offers]=await Promise.all([get('verified_pilot.geojson'),get('province.geojson'),get('offers.json')]);
 extent=L.geoJSON(province).getBounds();map.fitBounds(extent,{padding:[12,12]});
 for(const z of [...new Set(offers.map(o=>o.zoning))].sort())byId('zone').add(new Option(z,z));
 document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;draw();});
 for(const id of ['zone','budget','area'])byId(id).addEventListener('input',drawOffers);
 byId('reset').onclick=()=>{['zone','budget','area'].forEach(id=>byId(id).value='');drawOffers();};
 byId('extent').onclick=()=>map.fitBounds(extent,{padding:[12,12]});
 byId('csv').onclick=()=>{
  const fields=['label','lat','lon','posted','area','zoning','askingTL','heldOutRate','cluster'];
  const csv=[fields,...offers.map(o=>fields.map(k=>o[k]))].map(row=>row.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n');
  const u=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=u;a.download='Yalova_verified_offers.csv';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);
 };
 draw();
}
start().catch(e=>byId('caption').textContent=e.message);
