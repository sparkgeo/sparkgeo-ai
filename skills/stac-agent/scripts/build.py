#!/usr/bin/env python3
"""Build a static STAC Catalog from raster metadata and a collection config.

Usage:
    python3 build.py --metadata metadata.json --inventory inventory.json --config collection-config.yaml --output ./stac-output

Asset HREFs are set to the original S3 URIs — source data is never moved or copied.
Requires: pystac, shapely
"""

import argparse
import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pystac
import yaml
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

EXT_PROJ = "https://stac-extensions.github.io/projection/v2.0.0/schema.json"
EXT_RASTER = "https://stac-extensions.github.io/raster/v2.0.0/schema.json"
EXT_FILE = "https://stac-extensions.github.io/file/v2.1.0/schema.json"
EXT_EO = "https://stac-extensions.github.io/eo/v2.0.0/schema.json"

SIDECAR_MEDIA_TYPES = {
    ".aux.xml": "application/xml",
    ".json": "application/json",
    ".png": "image/png",
    ".xml": "application/xml",
}


def clean_id(name: str) -> str:
    name = re.sub(r"\.(tiff?|TIFF?)$", "", name)
    return re.sub(r"[^a-zA-Z0-9_-]", "-", name).lower().strip("-")


def _item_base(meta: dict, bands_config: list | None) -> pystac.Item:
    """Create a bare Item with projection/raster/eo properties set from meta."""
    geom = meta.get("geometry") or mapping(box(*meta["bbox_wgs84"]))
    bbox = meta["bbox_wgs84"]
    dt_str = meta.get("inferred_datetime")
    dt = datetime.fromisoformat(dt_str) if dt_str else None

    extensions = [EXT_PROJ, EXT_RASTER, EXT_FILE]

    # pystac >= 1.10 validates at construction: datetime=None requires string start/end datetimes.
    # When no date is parseable from the filename we use an open-ended sentinel range so the Item
    # remains schema-valid; callers can override via temporal_hint in collection-config.yaml.
    if dt:
        init_props: dict = {}
    else:
        temporal_hint = meta.get("_temporal_hint", {})
        init_props = {
            "datetime": None,
            "start_datetime": temporal_hint.get("start", "0001-01-01T00:00:00Z"),
            "end_datetime": temporal_hint.get("end", "9999-12-31T23:59:59Z"),
        }

    item = pystac.Item(
        id="",  # caller sets id
        geometry=geom,
        bbox=bbox,
        datetime=dt,
        properties=init_props,
        stac_extensions=extensions,
    )

    if meta.get("crs_epsg"):
        item.properties["proj:code"] = f"EPSG:{meta['crs_epsg']}"
    item.properties["proj:shape"] = [meta["height"], meta["width"]]

    return item


def build_item(meta: dict, size_map: dict, bands_config: list | None) -> pystac.Item:
    """One Item per raster file (one-per-file mode)."""
    uri = meta["uri"]
    item = _item_base(meta, bands_config)
    item.id = clean_id(uri.split("/")[-1])

    if size_map.get(uri):
        item.properties["file:size"] = size_map[uri]

    raster_bands = []
    for _ in range(meta["band_count"]):
        b = {"data_type": meta["dtype"]}
        if meta.get("nodata") is not None:
            b["nodata"] = meta["nodata"]
        if meta.get("resolution"):
            b["raster:spatial_resolution"] = meta["resolution"][0]
        raster_bands.append(b)
    if bands_config and len(bands_config) == len(raster_bands):
        for i, eo in enumerate(bands_config):
            if "name" in eo:
                raster_bands[i]["name"] = eo["name"]
            for key in ("common_name", "center_wavelength", "full_width_half_max", "solar_illumination"):
                if key in eo:
                    raster_bands[i][f"eo:{key}"] = eo[key]
        item.stac_extensions.append(EXT_EO)
    item.add_asset(
        "data",
        pystac.Asset(
            href=uri,
            media_type=meta["media_type"],
            roles=["data"],
            title=uri.split("/")[-1],
            extra_fields={"bands": raster_bands} if raster_bands else {},
        ),
    )
    return item


def group_by_prefix(metadata_list: list) -> dict:
    """Group rasters by their parent directory (scene prefix)."""
    groups = {}
    for meta in metadata_list:
        prefix = "/".join(meta["uri"].split("/")[:-1])
        groups.setdefault(prefix, []).append(meta)
    return groups


def identify_primary(metas: list, prefix: str) -> dict:
    """Primary = raster whose filename stem matches the parent directory name.
    Falls back to the raster with the shortest filename."""
    dir_name = prefix.split("/")[-1]
    for meta in metas:
        stem = re.sub(r"\.(tiff?|TIFF?)$", "", meta["uri"].split("/")[-1])
        if stem == dir_name:
            return meta
    return min(metas, key=lambda m: len(m["uri"].split("/")[-1]))


def build_item_group(
    prefix: str,
    metas: list,
    size_map: dict,
    sidecars: list,
    bands_config: list | None,
    sidecar_roles_cfg: dict,
) -> pystac.Item:
    """One Item per directory prefix, with all rasters and sidecars as assets."""
    primary = identify_primary(metas, prefix)
    item = _item_base(primary, bands_config)
    item.id = clean_id(prefix.split("/")[-1])

    if size_map.get(primary["uri"]):
        item.properties["file:size"] = size_map[primary["uri"]]

    # Primary raster
    raster_bands = []
    for _ in range(primary["band_count"]):
        b = {"data_type": primary["dtype"]}
        if primary.get("nodata") is not None:
            b["nodata"] = primary["nodata"]
        if primary.get("resolution"):
            b["raster:spatial_resolution"] = primary["resolution"][0]
        raster_bands.append(b)
    if bands_config and len(bands_config) == len(raster_bands):
        for i, eo in enumerate(bands_config):
            if "name" in eo:
                raster_bands[i]["name"] = eo["name"]
            for key in ("common_name", "center_wavelength", "full_width_half_max", "solar_illumination"):
                if key in eo:
                    raster_bands[i][f"eo:{key}"] = eo[key]
        item.stac_extensions.append(EXT_EO)
    item.add_asset(
        "data",
        pystac.Asset(
            href=primary["uri"],
            media_type=primary["media_type"],
            roles=["data"],
            title=primary["uri"].split("/")[-1],
            extra_fields={"bands": raster_bands} if raster_bands else {},
        ),
    )

    # Additional rasters — asset key from cleaned filename (strips .tif/.tiff)
    for meta in metas:
        if meta["uri"] == primary["uri"]:
            continue
        fname = meta["uri"].split("/")[-1]
        item.add_asset(
            clean_id(fname),
            pystac.Asset(
                href=meta["uri"],
                media_type=meta.get("media_type", "image/tiff; application=geotiff"),
                roles=["data"],
                title=fname,
            ),
        )

    # Sidecars — roles driven by sidecar_roles config, key from full filename
    for sidecar in sidecars:
        uri = sidecar["uri"]
        fname = uri.split("/")[-1]
        lower = fname.lower()
        roles = ["metadata"]
        for ext, cfg_roles in sidecar_roles_cfg.items():
            if lower.endswith(ext.lower()):
                roles = cfg_roles
                break
        media_type = next(
            (mt for ext, mt in SIDECAR_MEDIA_TYPES.items() if lower.endswith(ext)),
            None,
        )
        item.add_asset(
            clean_id(fname),
            pystac.Asset(href=uri, media_type=media_type, roles=roles, title=fname),
        )

    return item


def build_catalog(metadata: list, config: dict, output_dir: str) -> pystac.Catalog:
    col_cfg = config["collection"]
    bands_config = config.get("bands")
    grouping_mode = config.get("grouping", {}).get("mode", "one-per-file")
    sidecar_roles_cfg = config.get("sidecar_roles", {})

    size_map = {}
    if config.get("_inventory"):
        for r in config["_inventory"].get("rasters", []):
            size_map[r["uri"]] = r["size"]

    valid_meta = [m for m in metadata if not m.get("error")]
    for m in metadata:
        if m.get("error"):
            print(f"  Skipping {m['uri']}: {m['error']}", file=sys.stderr)

    if grouping_mode == "group-by-prefix":
        sidecar_map = {}
        if config.get("_inventory"):
            for s in config["_inventory"].get("sidecars", []):
                prefix = "/".join(s["uri"].split("/")[:-1])
                sidecar_map.setdefault(prefix, []).append(s)

        groups = group_by_prefix(valid_meta)
        items = []
        for prefix, metas in groups.items():
            try:
                items.append(build_item_group(
                    prefix, metas, size_map,
                    sidecar_map.get(prefix, []),
                    bands_config, sidecar_roles_cfg,
                ))
            except Exception as e:
                print(f"  Skipping group {prefix}: {e}\n{traceback.format_exc()}", file=sys.stderr)
    else:
        items = [build_item(m, size_map, bands_config) for m in valid_meta]

    if not items:
        raise ValueError("No valid items to build — check inspect output for errors.")

    union_geom = unary_union([shape(i.geometry) for i in items])
    union_bbox = list(union_geom.bounds)

    all_dts = [i.datetime for i in items if i.datetime]
    t_start = min(all_dts) if all_dts else None
    t_end = max(all_dts) if all_dts else None

    providers = [
        pystac.Provider(name=p["name"], roles=p.get("roles", ["producer"]), url=p.get("url"))
        for p in col_cfg.get("providers", [])
    ]

    item_extensions = sorted(set().union(*(set(i.stac_extensions) for i in items)))
    collection_extensions = [e for e in item_extensions if not (e == EXT_RASTER and not bands_config)]

    collection = pystac.Collection(
        id=col_cfg["id"],
        title=col_cfg.get("title"),
        description=col_cfg["description"],
        license=col_cfg.get("license", "proprietary"),
        providers=providers,
        extent=pystac.Extent(
            spatial=pystac.SpatialExtent(bboxes=[union_bbox]),
            temporal=pystac.TemporalExtent(intervals=[[t_start, t_end]]),
        ),
        stac_extensions=collection_extensions,
    )
    if EXT_EO in item_extensions and bands_config:
        common_names = sorted({b["common_name"] for b in bands_config if "common_name" in b})
        center_wls = sorted({b["center_wavelength"] for b in bands_config if "center_wavelength" in b})
        summaries: dict = {}
        if common_names:
            summaries["eo:common_name"] = common_names
        if center_wls:
            summaries["eo:center_wavelength"] = center_wls
        if summaries:
            collection.summaries = pystac.Summaries(summaries)

    for item in items:
        collection.add_item(item)

    catalog = pystac.Catalog(
        id=f"{col_cfg['id']}-catalog",
        description=f"STAC Catalog for {col_cfg.get('title', col_cfg['id'])}",
    )
    catalog.add_child(collection)

    os.makedirs(output_dir, exist_ok=True)
    catalog.normalize_hrefs(output_dir)
    catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)

    print(f"Catalog:    {output_dir}/catalog.json", file=sys.stderr)
    print(f"Collection: {col_cfg['id']}/collection.json", file=sys.stderr)
    print(f"Items:      {len(items)}", file=sys.stderr)

    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--metadata", required=True, help="metadata.json from raster_inspect.py")
    parser.add_argument("--config", required=True, help="collection-config.yaml")
    parser.add_argument("--inventory", help="inventory.json from inventory.py (for file sizes and sidecars)")
    parser.add_argument("--output", "-o", default="./stac-output", help="Output directory (default ./stac-output)")
    args = parser.parse_args()

    with open(args.metadata) as f:
        metadata = json.load(f)

    with open(args.config) as f:
        config = yaml.safe_load(f)

    if args.inventory:
        with open(args.inventory) as f:
            config["_inventory"] = json.load(f)

    build_catalog(metadata, config, args.output)


if __name__ == "__main__":
    main()
