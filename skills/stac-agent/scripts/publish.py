#!/usr/bin/env python3
"""Upload a local STAC catalog tree to an S3 location.

Only .json files are uploaded — source raster data is never touched.

Usage:
    python3 publish.py ./stac-output/ s3://target-bucket/stac/

Credentials are read from the environment (AWS profile, env vars, IAM role, STS).
"""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import boto3


ITEM_MEDIA_TYPE = "application/geo+json"
CATALOG_MEDIA_TYPE = "application/json"
ITEM_NAMES = {"catalog.json", "collection.json"}


def content_type(filename: str) -> str:
    return CATALOG_MEDIA_TYPE if filename in ITEM_NAMES else ITEM_MEDIA_TYPE


def publish(local_dir: str, s3_uri: str, dry_run: bool = False) -> list[str]:
    parsed = urlparse(s3_uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise ValueError(f"Invalid S3 URI: {s3_uri!r} — must be in the form s3://bucket/prefix/")
    bucket = parsed.netloc
    base_key = parsed.path.lstrip("/").rstrip("/") + "/"

    s3 = boto3.client("s3")
    uploaded = []

    for root, _, files in os.walk(local_dir):
        for fname in sorted(files):
            if not fname.endswith(".json"):
                continue
            local_path = os.path.join(root, fname)
            rel = os.path.relpath(local_path, local_dir)
            key = base_key + rel.replace(os.sep, "/")
            ct = content_type(fname)

            if dry_run:
                print(f"  [dry-run] s3://{bucket}/{key}  ({ct})")
            else:
                s3.upload_file(
                    local_path, bucket, key,
                    ExtraArgs={"ContentType": ct},
                )
                print(f"  Uploaded s3://{bucket}/{key}")
            uploaded.append(f"s3://{bucket}/{key}")

    return uploaded


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("local_dir", help="Local STAC catalog directory")
    parser.add_argument("s3_uri", help="Target S3 URI (e.g. s3://bucket/stac/)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be uploaded without uploading")
    args = parser.parse_args()

    local_dir = Path(args.local_dir)
    catalog = local_dir / "catalog.json"
    if not catalog.exists():
        print(f"ERROR: {catalog} not found. Run build.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Publishing {local_dir} → {args.s3_uri}", file=sys.stderr)
    uploaded = publish(str(local_dir), args.s3_uri, dry_run=args.dry_run)
    print(f"\n{'Would upload' if args.dry_run else 'Uploaded'} {len(uploaded)} files.", file=sys.stderr)


if __name__ == "__main__":
    main()
