#!/usr/bin/env python3
"""Validate a STAC catalog with pystac[validate] and a heuristic best-practices check.

Usage:
    python3 validate.py ./stac-output/
    python3 validate.py ./stac-output/ --strict

Exit codes:
    0  all checks passed
    1  pystac validation errors found
    2  heuristic errors found
    3  both
"""

import argparse
import glob
import json
import sys
from pathlib import Path


def load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


HEURISTIC_CHECKS = [
    # (severity, code, message, test_fn)
    # test_fn receives (obj, path, all_items) and returns True if the issue exists
]


def heuristic_review(catalog_dir: str) -> list[dict]:
    issues = []
    all_json = glob.glob(f"{catalog_dir}/**/*.json", recursive=True)
    all_items = []

    for path in all_json:
        try:
            obj = load(path)
        except Exception:
            continue
        rel = str(Path(path).relative_to(catalog_dir))
        t = obj.get("type", "")

        if t in ("Collection", "Catalog"):
            desc = obj.get("description", "")
            if len(desc.strip()) < 10:
                issues.append({"severity": "WARNING", "code": "MISSING_DESCRIPTION",
                                "location": rel, "message": "Description is empty or too short."})

        if t == "Collection":
            if not obj.get("license"):
                issues.append({"severity": "WARNING", "code": "MISSING_LICENSE",
                                "location": rel, "message": "No license field."})
            if not obj.get("providers"):
                issues.append({"severity": "WARNING", "code": "MISSING_PROVIDER",
                                "location": rel, "message": "No providers listed."})
            interval = obj.get("extent", {}).get("temporal", {}).get("interval", [[None, None]])
            if interval == [[None, None]]:
                issues.append({"severity": "WARNING", "code": "MISSING_TEMPORAL",
                                "location": rel, "message": "Temporal extent is fully open (null/null)."})
            if not obj.get("extent", {}).get("spatial", {}).get("bbox"):
                issues.append({"severity": "WARNING", "code": "MISSING_SPATIAL",
                                "location": rel, "message": "Spatial extent bbox is missing."})

        if t == "Feature":
            all_items.append((rel, obj))
            props = obj.get("properties", {})
            has_dt = props.get("datetime") or (props.get("start_datetime") and props.get("end_datetime"))
            if not has_dt:
                issues.append({"severity": "WARNING", "code": "ITEM_NO_DATETIME",
                                "location": rel, "message": "Item has no datetime or start/end_datetime."})

            for aname, asset in obj.get("assets", {}).items():
                loc = f"{rel} › assets.{aname}"
                if not asset.get("roles"):
                    issues.append({"severity": "WARNING", "code": "ASSET_NO_ROLE",
                                    "location": loc, "message": "Asset has no roles."})
                if not asset.get("type"):
                    issues.append({"severity": "WARNING", "code": "ASSET_NO_MEDIA_TYPE",
                                    "location": loc, "message": "Asset has no media type."})

            exts = obj.get("stac_extensions", [])
            has_raster = any(
                "tiff" in a.get("type", "") for a in obj.get("assets", {}).values()
            )
            if has_raster and not any("projection" in e for e in exts):
                issues.append({"severity": "WARNING", "code": "MISSING_PROJ",
                                "location": rel, "message": "Raster asset present but projection extension missing."})
            if has_raster and not any("raster" in e for e in exts):
                issues.append({"severity": "INFO", "code": "MISSING_RASTER_EXT",
                                "location": rel, "message": "Raster asset present but raster extension not applied."})

            item_id = obj.get("id", "")
            if any(c in item_id for c in (" ", "/", "\\")):
                issues.append({"severity": "WARNING", "code": "UNCLEAR_ITEM_ID",
                                "location": rel, "message": f"Item ID '{item_id}' contains spaces or path separators."})

            for link in obj.get("links", []):
                href = link.get("href", "")
                if href and not href.startswith(("http", "s3://")):
                    target = Path(path).parent / href
                    if not target.exists():
                        issues.append({"severity": "ERROR", "code": "INVALID_LINK",
                                        "location": rel, "message": f"Relative link not found: {href}"})

    if len(all_items) > 500:
        issues.append({"severity": "INFO", "code": "FLAT_CATALOG",
                        "location": "catalog", "message": f"{len(all_items)} items in a single collection — consider partitioning."})

    return issues


def run_pystac_validation(catalog_dir: str) -> tuple[bool, str]:
    try:
        import pystac
        catalog_json = str(Path(catalog_dir) / "catalog.json")
        catalog = pystac.read_file(catalog_json)
        num_validated = catalog.validate_all()
        return True, f"Validated {num_validated} STAC object(s) — all passed."
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("catalog_dir", help="Path to the STAC catalog directory")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on any warning (not just errors)")
    args = parser.parse_args()

    sep = "=" * 60

    # pystac validation
    print(f"\n{sep}")
    print("pystac validation")
    print(sep)
    passed, validator_output = run_pystac_validation(args.catalog_dir)
    print(validator_output.strip())
    print(f"\nResult: {'PASSED' if passed else 'FAILED'}")

    # heuristic
    print(f"\n{sep}")
    print("Heuristic Best-Practices Report")
    print(sep)
    issues = heuristic_review(args.catalog_dir)

    if issues:
        for issue in issues:
            print(f"\n[{issue['severity']}] {issue['code']}")
            print(f"  {issue['location']}")
            print(f"  {issue['message']}")

        errors = [i for i in issues if i["severity"] == "ERROR"]
        warnings = [i for i in issues if i["severity"] == "WARNING"]
        infos = [i for i in issues if i["severity"] == "INFO"]
        print(f"\nSummary: {len(errors)} errors, {len(warnings)} warnings, {len(infos)} info")
    else:
        print("No issues found.")

    exit_code = 0
    if not passed:
        exit_code |= 1
    heuristic_errors = [i for i in issues if i["severity"] == "ERROR"]
    if heuristic_errors or (args.strict and issues):
        exit_code |= 2
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
