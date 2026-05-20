#!/usr/bin/env python3
"""Extract raster metadata from S3 objects via GDAL range requests (no full download).

Usage:
    python3 raster_inspect.py --inventory inventory.json [--sample 10] [--output metadata.json]
    python3 raster_inspect.py --inventory inventory.json --profile my-sso-profile --output metadata.json
    python3 raster_inspect.py s3://bucket/key.tif [s3://bucket/key2.tif ...]

Requires: boto3, rasterio, rio-cogeo, pyproj, shapely
Public buckets are detected automatically — no flags or credentials required.
For private buckets, pass --profile to select an AWS profile (required for SSO profiles).
"""

import argparse
import json
import re
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlparse

import boto3
import rasterio
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError
from pyproj import CRS
from rasterio.warp import transform_bounds
from rio_cogeo.cogeo import cog_validate
from shapely.geometry import box, mapping

DATE_PATTERNS = [
    (r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", "%Y-%m-%dT%H:%M:%S"),
    (r"(\d{4}-\d{2}-\d{2})", "%Y-%m-%d"),
    (r"(\d{8}T\d{6})", "%Y%m%dT%H%M%S"),
    (r"(\d{8})", "%Y%m%d"),
]

GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_INGESTED_BYTES_AT_OPEN": "32768",
    "CPL_VSIL_CURL_CACHE_SIZE": "200000000",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
}


def _is_public(bucket: str, prefix: str = "") -> bool:
    """Return True if the bucket allows anonymous list access."""
    try:
        boto3.client("s3", config=Config(signature_version=UNSIGNED)).list_objects_v2(
            Bucket=bucket, Prefix=prefix, MaxKeys=1
        )
        return True
    except ClientError:
        return False


def infer_datetime(uri: str) -> str | None:
    filename = uri.split("/")[-1]
    for pattern, fmt in DATE_PATTERNS:
        m = re.search(pattern, filename)
        if m:
            try:
                return datetime.strptime(m.group(1), fmt).replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
    return None


def inspect_one(uri: str, gdal_env: dict) -> dict:
    parsed = urlparse(uri)
    vsi_path = f"/vsis3/{parsed.netloc}{parsed.path}"

    try:
        is_cog, cog_errors, cog_warnings = cog_validate(vsi_path, config=gdal_env)
        with rasterio.Env(**gdal_env):
            with rasterio.open(vsi_path) as ds:
                crs = CRS.from_wkt(ds.crs.wkt) if ds.crs else None
                epsg = crs.to_epsg() if crs else None
                bbox_wgs84 = list(transform_bounds(ds.crs, "EPSG:4326", *ds.bounds)) if ds.crs else None
                geom = mapping(box(*bbox_wgs84)) if bbox_wgs84 else None
                res_x = abs(ds.transform.a)
                res_y = abs(ds.transform.e)

                return {
                    "uri": uri,
                    "width": ds.width,
                    "height": ds.height,
                    "band_count": ds.count,
                    "dtype": ds.dtypes[0],
                    "nodata": ds.nodata,
                    "crs_epsg": epsg,
                    "crs_wkt": ds.crs.wkt if ds.crs else None,
                    "bbox_wgs84": [round(v, 6) for v in bbox_wgs84] if bbox_wgs84 else None,
                    "geometry": geom,
                    "resolution": [res_x, res_y],
                    "has_overviews": any(ds.overviews(i) for i in ds.indexes),
                    "is_cog": is_cog,
                    "cog_errors": cog_errors,
                    "cog_warnings": cog_warnings,
                    "media_type": (
                        "image/tiff; application=geotiff; profile=cloud-optimized"
                        if is_cog and not cog_errors
                        else "image/tiff; application=geotiff"
                    ),
                    "inferred_datetime": infer_datetime(uri),
                    "error": None,
                }
    except Exception as exc:
        print(f"WARN: inspection failed for {uri}: {exc}\n{traceback.format_exc()}", file=sys.stderr)
        return {"uri": uri, "error": str(exc)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("uris", nargs="*", help="S3 URIs to inspect")
    parser.add_argument("--inventory", help="inventory.json produced by inventory.py")
    parser.add_argument("--sample", type=int, default=10, help="Max files to inspect (default 10)")
    parser.add_argument("--output", "-o", help="Write JSON to this file instead of stdout")
    parser.add_argument("--workers", type=int, default=5, help="Parallel workers (default 5)")
    parser.add_argument("--profile", default=None, help="AWS profile name for private buckets (required for SSO profiles)")
    args = parser.parse_args()

    if args.inventory:
        with open(args.inventory) as f:
            inv = json.load(f)
        uris = [r["uri"] for r in inv["rasters"][: args.sample]]
    elif args.uris:
        uris = args.uris[: args.sample]
    else:
        parser.error("Provide S3 URIs or --inventory")

    parsed = urlparse(uris[0])
    if _is_public(parsed.netloc, parsed.path.lstrip("/")):
        gdal_env = {**GDAL_ENV, "AWS_NO_SIGN_REQUEST": "YES"}
    elif args.profile:
        session = boto3.Session(profile_name=args.profile)
        creds = session.get_credentials().get_frozen_credentials()
        gdal_env = {
            **GDAL_ENV,
            "AWS_ACCESS_KEY_ID": creds.access_key,
            "AWS_SECRET_ACCESS_KEY": creds.secret_key,
            "AWS_SESSION_TOKEN": creds.token,
        }
    else:
        gdal_env = GDAL_ENV

    results = [None] * len(uris)
    print(f"Inspecting {len(uris)} files...", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(inspect_one, uri, gdal_env): i for i, uri in enumerate(uris)}
        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()
            status = "ok" if not results[i].get("error") else f"ERROR: {results[i]['error']}"
            print(f"  [{i+1}/{len(uris)}] {uris[i].split('/')[-1]} — {status}", file=sys.stderr)

    output = json.dumps(results, indent=2, default=str)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
