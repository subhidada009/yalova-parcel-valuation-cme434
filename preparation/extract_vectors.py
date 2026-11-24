"""Extract the project vectors from Geofabrik's dated Türkiye OSM PBF.

One-time preparation: python -m pip install osmium shapely pyproj
Run: python preparation/extract_vectors.py path/to/turkey-261122.osm.pbf layers
The PBF is national; approximately 2 GB of free memory is recommended.
"""
from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path
from datetime import date
import hashlib
import json

import osmium
from pyproj import Transformer
from shapely import from_wkb, make_valid
from shapely.geometry import LineString, Point, Polygon, box, mapping
from shapely.ops import polygonize, transform, unary_union

TAGS = {
    "road": [("highway", val) for val in ("motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link")],
    "transit": [("highway", "bus_stop"), ("public_transport", "platform"), ("public_transport", "stop_position"), ("amenity", "ferry_terminal"), ("amenity", "bus_station"), ("railway", "station"), ("railway", "halt")],
    "school": [("amenity", "school")],
    "hospital": [("amenity", "hospital"), ("healthcare", "hospital")],
    "park": [("leisure", "park")],
    "coast": [("natural", "coastline")],
    "centre": [("place", "city"), ("place", "town")],
}
TAG_PAIRS = [pair for pairs in TAGS.values() for pair in pairs]
RECENT_URL = "https://download.geofabrik.de/europe/turkey/"
SEARCH = box(28.45, 40.22, 29.85, 40.98)
FORWARD = Transformer.from_crs(4326, 32635, always_xy=True).transform
REVERSE = Transformer.from_crs(32635, 4326, always_xy=True).transform
BUFFER_M = 18000
GEOM = osmium.geom.WKBFactory()


def matches(tags):
    return [name for name, pairs in TAGS.items() if any(tags.get(k) == v for k, v in pairs)
            and (name != "centre" or tags.get("name") == "Yalova")]


def feature(osm_type, oid, geom):
    return {"type": "Feature", "properties": {"osm_type": osm_type, "osm_id": oid},
            "geometry": mapping(geom)}


def build_polygons(members, ways):
    rings = {"outer": [], "inner": []}
    for role, way in members:
        if way not in ways:
            return None
        rings[role].append(ways[way])
    outer = unary_union(list(polygonize(rings["outer"])))
    if outer.is_empty:
        return None
    if rings["inner"]:
        outer = outer.difference(unary_union(list(polygonize(rings["inner"]))))
    return make_valid(outer)


def terrestrial_boundary(province, coastlines, centre):
    """Split the area on mapped coasts. OSM coast ways run with land on the left."""
    crs_area = transform(FORWARD, province)
    coasts = [transform(FORWARD, geom) for geom in coastlines if geom.intersects(province)]
    topology = unary_union([crs_area.boundary, *coasts])
    coast_union = unary_union(coasts)
    pieces = [p for p in polygonize(topology) if crs_area.covers(p.representative_point())]
    mainland = transform(FORWARD, centre)
    result = []
    left_points = []
    for line in coasts:
        for a, b in zip(line.coords, list(line.coords)[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = (dx * dx + dy * dy) ** .5
            if length >= .1:
                left_points.append(Point((a[0]+b[0])/2-dy/length*.05, (a[1]+b[1])/2+dx/length*.05))
    for p in pieces:
        if p.covers(mainland) or (p.boundary.intersection(coast_union).length > .1
                                  and any(p.contains(pt) for pt in left_points)):
            result.append(p)
    result = unary_union(result)
    area = result.area / 1e6
    if not 700 < area < 950 or not result.covers(mainland):
        raise ValueError(f"Review land/coast topology before use (area {area:.1f} square km).")
    return transform(REVERSE, result), area


def extract(source, output):
    output.mkdir(exist_ok=True, parents=True)
    files = str(source)
    relations, attrs = {}, {}
    boundary_id = None
    for rel in osmium.FileProcessor(files, osmium.osm.RELATION).with_filter(
            osmium.filter.TagFilter(("ISO3166-2", "TR-77"), *TAG_PAIRS)):
        if rel.tags.get("type") not in ("boundary", "multipolygon"):
            continue
        classes = matches(rel.tags)
        if rel.tags.get("ISO3166-2") == "TR-77" and rel.tags.get("boundary") == "administrative":
            boundary_id = rel.id
            classes = ["boundary"]
        if classes:
            relations[rel.id] = [(m.role or "outer", m.ref) for m in rel.members
                                 if m.type == "w" and m.role in ("", "outer", "inner")]
            attrs[rel.id] = classes
    if boundary_id is None:
        raise ValueError("The selected file does not contain Yalova province (TR-77).")
    print("Reading regional facilities and national node locations.", flush=True)
    objects = defaultdict(list)
    nodes = osmium.FileProcessor(files, osmium.osm.NODE).with_locations("sparse_mem_array")
    for n in nodes.with_filter(osmium.filter.TagFilter(*TAG_PAIRS)):
        xy = n.location.lon, n.location.lat
        if not (SEARCH.bounds[0] <= xy[0] <= SEARCH.bounds[2] and SEARCH.bounds[1] <= xy[1] <= SEARCH.bounds[3]):
            continue
        for kind in matches(n.tags):
            objects[kind].append(("node", n.id, Point(xy)))
    locations = osmium.NodeLocationsForWays(nodes.node_location_storage)
    locations.ignore_errors()
    index = {}
    print("Assembling boundary and facility relations.", flush=True)
    way_ids = {way for members in relations.values() for _, way in members}
    for w in osmium.FileProcessor(files, osmium.osm.WAY).with_filter(osmium.filter.IdFilter(way_ids)).with_filter(locations):
        try:
            line = from_wkb(GEOM.create_linestring(w))
        except (RuntimeError, osmium.InvalidLocationError):
            continue
        if SEARCH.intersects(line):
            index[w.id] = line
    province = build_polygons(relations[boundary_id], index)
    if province is None:
        raise ValueError("The regional boundary has missing members.")
    for rid, members in relations.items():
        if rid == boundary_id or not members:
            continue
        polygon = build_polygons(members, index)
        if polygon is not None:
            for kind in attrs[rid]:
                objects[kind].append(("relation", rid, polygon))
    print("Reading tagged transport, shoreline and service ways.", flush=True)
    for w in osmium.FileProcessor(files, osmium.osm.WAY).with_filter(osmium.filter.TagFilter(*TAG_PAIRS)).with_filter(locations):
        try:
            line = from_wkb(GEOM.create_linestring(w))
        except (RuntimeError, osmium.InvalidLocationError):
            continue
        if not SEARCH.intersects(line):
            continue
        for kind in matches(w.tags):
            shape = (make_valid(Polygon(line)) if line.is_ring and kind in ("school", "hospital", "park", "transit")
                     and w.tags.get("area") != "no" else line)
            objects[kind].append(("way", w.id, shape))
    if len(objects["centre"]) != 1:
        raise ValueError(f"Expected a unique Yalova city node; found {len(objects['centre'])}.")
    centre = objects["centre"][0][2]
    boundary, area = terrestrial_boundary(province, [g for _,_,g in objects["coast"]], centre)
    catchment = transform(REVERSE, transform(FORWARD, boundary).buffer(BUFFER_M))
    if not SEARCH.covers(catchment):
        raise ValueError("The extraction window is smaller than the accessibility buffer.")
    objects["boundary"] = [("relation", boundary_id, boundary)]
    counts = {}
    for kind, records in objects.items():
        features = []
        for osm_type, oid, geom in records:
            geom = geom.intersection(catchment) if kind not in ("boundary", "centre") else geom
            if not geom.is_empty:
                features.append(feature(osm_type, oid, geom))
        if not features:
            raise ValueError(f"No features extracted for {kind}.")
        counts[kind] = len(features)
        (output / f"{kind}.geojson").write_text(json.dumps(
            {"type":"FeatureCollection", "name":kind, "features":features}, separators=(",", ":")), encoding="utf-8")
    head = osmium.FileProcessor(files).header
    snapshot = head.get("osmosis_replication_timestamp")
    stamp = snapshot[:10].replace("-", "")[2:]
    digest = hashlib.file_digest(source.open("rb"), "md5").hexdigest()
    manifest = {
        "source": "© OpenStreetMap contributors, distributed by Geofabrik",
        "license": "Open Database License (ODbL) 1.0",
        "license_url": "https://www.openstreetmap.org/copyright",
        "source_url": f"{RECENT_URL}turkey-{stamp}.osm.pbf",
        "archive_checksum_md5": digest, "snapshot_utc": snapshot,
        "extracted_on": date.today().isoformat(),
        "coordinate_reference_system": "EPSG:4326",
        "spatial_resolution": "Vector geometry; mapping precision and coverage vary by feature.",
        "accessibility_buffer_m": BUFFER_M,
        "buffer_method": "Terrestrial province polygon buffered in EPSG:32635; all matching features clipped to the buffer.",
        "boundary_method": "OSM administrative relation TR-77 intersected with land inferred from directed coastline ways; projected topology, city-node containment and area sanity checks.",
        "province_relation_id": boundary_id,
        "land_area_km2": round(area, 3), "bounds_wgs84": list(boundary.bounds),
        "centre_definition": "OSM place=city or town node named Yalova. Proxy for the provincial urban centre.",
        "centre_osm_url": f"https://www.openstreetmap.org/node/{objects['centre'][0][1]}",
        "centre_wgs84": list(centre.coords[0]),
        "selection_tags": TAGS, "feature_counts": counts,
        "limitations": "OSM is a contributor-maintained map. Distances are straight-line distance to the mapped geometry, not travel times. Roads exclude tertiary and local streets. Transit coverage depends on mapped stops. The 18 km external buffer includes nearby facilities outside Yalova. The OSM boundary is suitable for study, not cadastral or legal use."
    }
    (output/"vector_sources.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("pbf", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    extract(args.pbf, args.output)
