// Run in the Google Earth Engine Code Editor using a registered Earth Engine project.
// Grid cells and parcel buffers are clipped to the local terrestrial boundary
// by the Python backend. The rectangular export includes a buffer at every edge.
var frame = ee.Geometry.Rectangle([28.70, 40.44, 29.69, 40.77], null, false);
var crs = 'EPSG:32635';
var step = 30;
var start = '2026-10-25';
var endExclusive = '2026-11-24';
var rgbDate = '2026-11-09';
var folder = 'CME434_Yalova';
var srName = 'COPERNICUS/S2_SR_HARMONIZED';
var dwName = 'GOOGLE/DYNAMICWORLD/V1';
var sr = ee.ImageCollection(srName).filterBounds(frame).filterDate(start, endExclusive);
var land = ee.ImageCollection(dwName).filterBounds(frame).filterDate(start, endExclusive);

function ratio(a, b, name) {
  var total = a.add(b);
  return a.subtract(b).divide(total)
    .updateMask(total.gt(0)).rename(name).toFloat();
}

function spectralLayers(image) {
  var scl = image.select('SCL');
  var clear = scl.eq(4).or(scl.eq(5)).or(scl.eq(6));
  // Each granule is calculated on its SWIR 20 m grid. Continuous reflectance
  // is bilinearly resampled. SCL uses its native nearest-neighbour classes.
  var nativeGrid = image.select('B11').projection();
  var refl = image.select(['B3', 'B4', 'B8', 'B11']).updateMask(clear)
    .resample('bilinear').reproject(nativeGrid).multiply(0.0001);
  var nir = refl.select('B8');
  var swir = refl.select('B11');
  return ee.Image.cat([ratio(nir, refl.select('B4'), 'ndvi'),
                       ratio(swir, nir, 'ndbi'),
                       ratio(refl.select('B3'), swir, 'mndwi')])
    .copyProperties(image, ['system:time_start']);
}

var rgbDay = sr.filterDate(rgbDate, ee.Date(rgbDate).advance(1, 'day'))
  .filter(ee.Filter.eq('SPACECRAFT_NAME', 'Sentinel-2C'))
  .filter(ee.Filter.inList('MGRS_TILE', ['35TPE', '35TPF', '35TQE', '35TQF']));
var rgbStyle = {bands: ['B4', 'B3', 'B2'], min: 0, max: 3000, gamma: 1.1};
var rgb = rgbDay.sort('system:index').mosaic().clip(frame);
Map.centerObject(frame, 10);
Map.addLayer(rgb, rgbStyle, 'Sentinel-2C RGB | 9 November 2026');
Map.add(ui.Label('Yalova Province  |  Sentinel-2C RGB  |  9 November 2026 UTC', {
  position: 'bottom-left', padding: '7px 10px', fontWeight: 'bold'
}));

// Common time window, independent temporal medians per pixel. Dynamic World
// probabilities are soft predictions, not class labels or percentages of land.
var optical = sr.map(spectralLayers).median();
var probabilities = land.map(function(image) {
  return image.select(['built', 'trees', 'crops'],
    ['built_probability', 'tree_probability', 'crop_probability'])
    .resample('bilinear').toFloat();
}).median();
var names = ['ndvi', 'ndbi', 'mndwi',
             'built_probability', 'tree_probability', 'crop_probability'];
var stack = optical.addBands(probabilities).select(names).clip(frame).toFloat();
Map.addLayer(stack.select('ndvi'), {min: -0.4, max: 0.8,
  palette: ['473e52', 'e2d7ad', '42866b', '174b3c']}, 'Median NDVI', false);
Map.addLayer(stack.select('built_probability'), {min: 0, max: 1,
  palette: ['f5f6ee', 'bb6657', '64283c']}, 'Median built probability', false);
print('RGB acquisition date (UTC)', rgbDate);
print('RGB granule IDs', rgbDay.aggregate_array('system:index'));
print('Sentinel-2 and Dynamic World candidate counts', sr.size(), land.size());
print('Band order, first to sixth', stack.bandNames());

Export.image.toDrive({
  image: stack.unmask(-9999, false), description: 'Yalova_environment',
  folder: folder, fileNamePrefix: 'environment', region: frame, crs: crs,
  scale: step, maxPixels: 1e9, fileFormat: 'GeoTIFF',
  formatOptions: {cloudOptimized: true, noData: -9999}
});
Export.image.toDrive({
  image: rgb.visualize(rgbStyle), description: 'Yalova_RGB_20261109',
  folder: folder, fileNamePrefix: 'sentinel2_rgb_2026-11-09',
  region: frame, crs: crs, scale: step, maxPixels: 1e9,
  fileFormat: 'GeoTIFF', formatOptions: {cloudOptimized: true}
});

function inventory(collection, collectionName, role) {
  return ee.FeatureCollection(collection.toList(collection.size()).map(function(entry) {
    var image = ee.Image(entry);
    return ee.Feature(null, {
      source: collectionName, role: role, asset_id: image.get('system:index'),
      utc: image.date().format("YYYY-MM-dd'T'HH:mm:ss'Z'"),
      window_start: start, window_end_exclusive: endExclusive,
      output_crs: crs, output_grid_m: step
    });
  }));
}
var sources = inventory(sr, srName, 'spectral window')
  .merge(inventory(land, dwName, 'probability window'))
  .merge(inventory(rgbDay, srName, 'RGB display'));
Export.table.toDrive({collection: sources, description: 'Yalova_satellite_inventory',
  folder: folder, fileNamePrefix: 'satellite_inventory', fileFormat: 'CSV',
  selectors: ['source', 'role', 'asset_id', 'utc', 'window_start',
    'window_end_exclusive', 'output_crs', 'output_grid_m']});
