---
name: stac-agent
description: Build and validate a static STAC Catalog from GeoTIFF/COG raster files at an S3 location (public or private). Covers inventory, raster inspection, STAC Item/Collection/Catalog creation, validation, and optional publishing. Source data is never moved, copied, or transformed. Trigger phrases- "build STAC from S3", "create catalog from S3", "inventory S3 rasters", "STAC from bucket", "validate STAC catalog".
compatibility: Requires uv and AWS CLI. Public buckets need no credentials. Private buckets require boto3-resolvable credentials from the environment.
allowed-tools: Bash(aws sts get-caller-identity) Bash(aws s3 ls *) Bash(aws s3 cp *) Bash(uv venv *) Bash(uv pip *) Bash(.stac-venv/bin/python *) Read Write
---

# STAC Agent

Build a static STAC Catalog from GeoTIFF/COG rasters at an S3 location (public or private).
Source data is **never** moved, copied, or transformed. All asset HREFs point to the original S3 URIs.

**Arguments:** `$ARGUMENTS`
Parse into: `S3_SOURCE` (required) and `OUTPUT_PATH` (optional, default `./stac-output`).

---

## Ground rules

- Public S3 buckets need no credentials — the skill auto-detects them and uses anonymous access. Private buckets require credentials from the environment; never request, accept, or configure credentials yourself. If a private bucket's credentials are absent or expired, halt with a clear alert (see Step 0).
- Never move, copy, transform, rewrite, or upload source raster assets. Asset HREFs stay as `s3://` URIs throughout.
- Use `proj:code` (e.g. `"EPSG:32610"`), never the deprecated `proj:epsg`.
- COG media type: `image/tiff; application=geotiff; profile=cloud-optimized`
- STAC version: 1.1.0. Use pystac for object construction.
- Inspect first, ask questions later.
- Validation is a hard completion gate — STAC output is not finished until `validate.py` passes.
- Always create and use `.stac-venv/` for dependencies (`uv venv .stac-venv`). Never install packages to the system Python.
- **No new scripts or inline code.** The scripts in `scripts/` cover the full pipeline. Never write ad-hoc Python or shell code to build, inspect, validate, or publish STAC objects. If an edge case requires a script change, propose the targeted modification and wait for user approval.
- **No `stac-validator` CLI.** Do not `pip install stac-validator` or invoke it. `validate.py` uses `pystac[validation]` internally — that is the only permitted validation path.
- **Venv is mandatory.** All Python invocations must use `.stac-venv/bin/python`. Never call `python3`, `python`, or any system/conda interpreter directly.
- **No git operations.** Never commit, push, or modify git history — version control is the user's responsibility.
- **Check for existing metadata first.** Before asking for any metadata, scan the working directory and S3 path prefix for README, LICENSE files, `collection-config.yaml`, sidecar XMLs/JSONs, and existing STAC catalog files. Use what's there.
- **Scripts have `--help`.** If a script's interface is unclear, run `scripts/<name>.py --help` to discover flags and usage before invoking it.
- **STAC extensions.** Always apply the correct extension schema URLs. Items always get Projection v2.0.0, Raster v2.0.0, and File v2.1.0. EO v2.0.0 is added only when band config is provided. HSI v1.0.0 is added only for hyperspectral data (>10 bands with wavelength semantics). Collections must declare the same extensions as their items.

  | Extension | Schema URL |
  |---|---|
  | Projection v2.0.0 | `https://stac-extensions.github.io/projection/v2.0.0/schema.json` |
  | Raster v2.0.0 | `https://stac-extensions.github.io/raster/v2.0.0/schema.json` |
  | File v2.1.0 | `https://stac-extensions.github.io/file/v2.1.0/schema.json` |
  | EO v2.0.0 | `https://stac-extensions.github.io/eo/v2.0.0/schema.json` |
  | HSI v1.0.0 | `https://stac-extensions.github.io/hsi/v1.0.0/schema.json` |

---

## Default workflow

Unless the user asks only to validate an existing catalog, always run in order:

```
scripts/inventory.py      → inventory.json
scripts/raster_inspect.py → metadata.json
[Q&A — semantic metadata only]
scripts/build.py          → <OUTPUT_PATH>/
scripts/validate.py       → must pass (exit 0)
```

Run `scripts/publish.py` only when the user explicitly requests publishing or when `OUTPUT_PATH` starts with `s3://`.

---

## Step 0 — Bucket access check

Verify the bucket is reachable before installing dependencies:

```bash
aws s3 ls <S3_SOURCE> --no-sign-request 2>/dev/null || aws s3 ls <S3_SOURCE> 2>/dev/null || echo "UNREACHABLE"
```

If neither command succeeds, **stop immediately** and print:

> Cannot access `<S3_SOURCE>`.
> - Public bucket: verify the URI is correct.
> - Private bucket: configure credentials (AWS_PROFILE, AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, or SSO session), then rerun.

The pipeline scripts (`inventory.py`, `raster_inspect.py`) detect public vs. private access automatically — no flags needed.

Never run `aws configure`, `aws sso login`, or any credential-setup command. Credential management is the user's responsibility.

---

## Step 1 — Prerequisites and S3 access

Create an isolated virtual environment and install dependencies:

```bash
uv venv .stac-venv
uv pip install -q boto3 rasterio rio-cogeo "pystac[validation]" shapely pyproj pyyaml
aws --version
```

All subsequent Python invocations use `.stac-venv/bin/python`. Do not use `python3` or `uv run` directly.

Access was confirmed in Step 0. No additional S3 check needed here.

---

## Step 2 — Inventory

If `inventory.json` already exists in the working directory, skip this step and use the cached file. Only rerun if the user explicitly requests a fresh inventory or the S3 path has changed. Never call `aws s3 ls` manually to browse the bucket — `inventory.py` handles all S3 listing.

```bash
.stac-venv/bin/python scripts/inventory.py <S3_SOURCE> --output inventory.json
```

Report raster count, sidecar count, and total size. If no rasters are found, stop and ask the user to confirm the path.

---

## Step 3 — Inspect

If `metadata.json` already exists, skip this step and use the cached file. Only rerun if `inventory.json` has changed or the user requests a fresh inspection. Do not open, parse, or download raster files outside of `raster_inspect.py`.

Use `--sample 10` for datasets with many rasters. Increase only if the sample reveals mixed CRS, inconsistent band counts, or date-parsing failures across the full set.

```bash
.stac-venv/bin/python scripts/raster_inspect.py --inventory inventory.json --sample 10 --output metadata.json
```

Summarise what was inferred **before asking any questions**:

| Property | Inferred value |
|---|---|
| CRS | EPSG:XXXXX |
| Raster dimensions | W × H px |
| Bands / dtype | N bands, dtype |
| COG status | yes / no / mixed |
| Dates in filenames | found / not found |
| bbox (WGS84) | [W, S, E, N] |

Note any files that failed inspection.

---

## Step 4 — Clarification Q&A

If the user supplied `--config collection-config.yaml`, skip this step.

**Before asking — scan for existing metadata:**
Check the working directory and S3 path prefix for `collection-config.yaml`, README, LICENSE files, sidecar XMLs or JSONs, and existing STAC catalog files. Pre-fill any answers already present in those files.

**Infer without asking (mechanical metadata):**
bbox, geometry, CRS, proj:code, projection metadata, raster dimensions, bands, data type, media type, COG status, dates clearly parseable from filenames.

**Must not invent (semantic metadata) — always ask if not already found:**
1. Collection title
2. Collection description (1–3 sentences)
3. License — check for `LICENSE`, `LICENSE.txt`, or `LICENSE.md` first; use the license name found, or default to `proprietary` if nothing is found
4. Provider name and role — Sparkgeo is always added as a `processor` provider; ask for any additional data provider

**Ask only if unresolved:**
5. Grouping mode — one Item per file, or multiple files per Item
6. Band semantics — only if band count > 1 and no known sensor pattern detected
7. Temporal hint — only if no dates found in any filenames
8. Sidecar roles — only if sidecar files exist

Write confirmed answers to `collection-config.yaml` using `templates/collection-config.yaml` as a guide.

---

## Step 5 — Build

```bash
.stac-venv/bin/python scripts/build.py \
  --metadata metadata.json \
  --inventory inventory.json \
  --config collection-config.yaml \
  --output <OUTPUT_PATH>
```

Produces `catalog.json`, `<collection-id>/collection.json`, and one JSON file per Item.
Asset HREFs are the original S3 URIs — nothing is uploaded or copied.

---

## Step 6 — Validate

```bash
.stac-venv/bin/python scripts/validate.py <OUTPUT_PATH>
```

This is a **hard gate**. Do not report success until exit code is 0. `validate.py` uses `pystac[validation]` for schema validation — do not install or run `stac-validator` separately.

If validation fails:
- **Deterministic errors** (broken links, missing media types, malformed IDs): fix directly and rerun.
- **Semantic gaps** (missing license, ambiguous datetime): ask the user for the missing information, then fix and rerun.

---

## Step 7 — Publish (conditional)

Run only when the user explicitly requests publishing, or when `OUTPUT_PATH` starts with `s3://`.
Always complete Steps 5 and 6 first.

If `OUTPUT_PATH` is an S3 URI, build to a local temp directory, validate, then publish:

```bash
.stac-venv/bin/python scripts/build.py ... --output /tmp/stac-output
.stac-venv/bin/python scripts/validate.py /tmp/stac-output
.stac-venv/bin/python scripts/publish.py /tmp/stac-output <OUTPUT_PATH>
```

`publish.py` uploads `.json` files only. Source raster data is never touched.

---

## Step 8 — Report

```
STAC Agent — Complete
=====================
Source:           <S3_SOURCE>
Output:           <OUTPUT_PATH>
Items:            N
Collections:      N
Validation:       PASSED
Assumptions made: [list of inferred mechanical values]
Unresolved gaps:  [missing semantic metadata, or "none"]
Published to:     <S3 destination, or "not published">
```

---

## Metadata inference rules

| Safe to infer (mechanical) | Must ask (semantic) |
|---|---|
| bbox, geometry | license (check LICENSE file first; default `proprietary`) |
| CRS / proj:code | providers (Sparkgeo processor always included; ask for data provider) |
| projection metadata (shape, transform) | collection description |
| raster dimensions, bands, dtype | scientific methodology |
| media type, COG status | platform / instrument |
| dates clearly parseable from filenames | ambiguous temporal ranges |
| | keywords |

---

## Supporting files

| File | Purpose |
|---|---|
| `scripts/inventory.py` | List and classify S3 objects |
| `scripts/raster_inspect.py` | Extract raster metadata via range requests |
| `scripts/build.py` | Construct pystac Catalog → Collection → Items |
| `scripts/validate.py` | pystac[validation] + heuristic checks |
| `scripts/publish.py` | Upload local STAC JSON tree to S3 (never touches source data) |
| `templates/collection-config.yaml` | Config template to bypass Q&A |
| `examples/` | Reference output shapes only — do not copy identifiers, descriptions, providers, licenses, or other semantic values |
