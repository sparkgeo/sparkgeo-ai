#!/usr/bin/env python3
"""List and classify objects under an S3 prefix.

Usage:
    python3 inventory.py s3://bucket/prefix/
    python3 inventory.py s3://bucket/prefix/ --output inventory.json
    python3 inventory.py s3://bucket/prefix/ --profile my-sso-profile --output inventory.json

Output (stdout or file): JSON object with rasters, sidecars, ignored lists.
Public buckets are detected automatically — no flags or credentials required.
For private buckets, pass --profile to select an AWS profile (required for SSO profiles).
"""

import argparse
import json
import sys
from urllib.parse import urlparse

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError

RASTER_EXTS = {".tif", ".tiff"}
SIDECAR_EXTS = {".xml", ".json", ".txt", ".imd", ".rpb", ".ovr", ".aux", ".png"}


def classify(key: str) -> str:
    lower = key.lower()
    if lower.endswith(tuple(RASTER_EXTS)):
        return "raster"
    if any(lower.endswith(e) for e in SIDECAR_EXTS) or lower.endswith(".aux.xml"):
        return "sidecar"
    return "ignored"


def _make_client(bucket: str, prefix: str, profile: str | None = None) -> boto3.client:
    """Try anonymous access first; fall back to the credential chain for private buckets."""
    anon = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    try:
        anon.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
        return anon
    except ClientError:
        return boto3.Session(profile_name=profile).client("s3")


def run(s3_uri: str, profile: str | None = None) -> dict:
    parsed = urlparse(s3_uri)
    bucket = parsed.netloc
    prefix = parsed.path.lstrip("/")

    s3 = _make_client(bucket, prefix, profile)
    paginator = s3.get_paginator("list_objects_v2")

    rasters, sidecars, ignored = [], [], []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            record = {
                "key": key,
                "uri": f"s3://{bucket}/{key}",
                "size": obj["Size"],
                "etag": obj["ETag"].strip('"'),
                "last_modified": obj["LastModified"].isoformat(),
            }
            kind = classify(key)
            if kind == "raster":
                rasters.append(record)
            elif kind == "sidecar":
                sidecars.append(record)
            else:
                ignored.append(record)

    return {
        "bucket": bucket,
        "prefix": prefix,
        "rasters": rasters,
        "sidecars": sidecars,
        "ignored": ignored,
        "total_raster_bytes": sum(r["size"] for r in rasters),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("s3_uri", help="S3 URI to inventory (e.g. s3://bucket/prefix/)")
    parser.add_argument("--output", "-o", help="Write JSON to this file instead of stdout")
    parser.add_argument("--profile", default=None, help="AWS profile name for private buckets (required for SSO profiles)")
    args = parser.parse_args()

    result = run(args.s3_uri, args.profile)

    mb = result["total_raster_bytes"] / 1e6
    print(f"Rasters:  {len(result['rasters'])} files  ({mb:.1f} MB)", file=sys.stderr)
    print(f"Sidecars: {len(result['sidecars'])} files", file=sys.stderr)
    print(f"Ignored:  {len(result['ignored'])} files", file=sys.stderr)

    output = json.dumps(result, indent=2, default=str)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
