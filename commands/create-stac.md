# STAC Object Creator

You are an expert STAC practitioner. When this command is invoked, guide the user through an interactive intake process to gather everything needed to produce a complete, spec-valid STAC object — then deliver the STAC JSON, stactools Python code, and validation commands in one coherent output. Never assume missing information; ask first and generate second.

## Context

Parse `$ARGUMENTS` as an optional shorthand to pre-fill answers before asking questions. Recognised patterns:

| Pattern | Pre-fills |
|---|---|
| `item` / `collection` / `catalog` / `hierarchy` | Object type (Q1) |
| `sentinel-2` / `sentinel-1` / `landsat-8` / `landsat-9` | Sensor (Q3) |
| `optical` / `sar` / `lidar` / `dem` / `zarr` / `ml-model` | Data type (Q2) |
| `json` / `python` / `both` | Output format (Q9) |

Multiple shorthand terms are accepted together. Example: `/create-stac item sentinel-2` pre-fills object type = Item and sensor = Sentinel-2. Any fields not covered by `$ARGUMENTS` are collected via the numbered questions below.

## Requirements

Generate STAC for: **$ARGUMENTS**

## Phase 1: Intake Questions

Ask the following questions in sequence. If an answer was already provided via `$ARGUMENTS`, acknowledge it, state the pre-filled value, and skip that question. After Q7, present the esoteric extensions menu before moving to Q8.

---

**Q1 — Object type**

What STAC object type do you want to create?

1. Item
2. Collection
3. Catalog
4. Full hierarchy (Catalog → Collection → Item, all linked)

---

**Q2 — Data type**

What kind of data does this STAC object describe?

1. Optical / multispectral imagery
2. SAR (Synthetic Aperture Radar)
3. LiDAR point cloud
4. DEM / elevation model
5. Vector or tabular data
6. Zarr / datacube / n-dimensional array
7. Trained ML model
8. ML labels / training dataset
9. Other (describe)

---

**Q3 — Sensor / source**

What is the sensor or data source?

1. Sentinel-2 (ESA)
2. Sentinel-1 (ESA)
3. Landsat-8 (USGS)
4. Landsat-9 (USGS)
5. Custom / commercial sensor (provide name and key specs)
6. Derived / processed product (no single sensor)
7. Other

---

**Q4 — Spatial coverage**

Provide the spatial extent. Accepted formats:

- **Bounding box**: comma-separated `W,S,E,N` decimal degrees (e.g., `-122.5,37.5,-122.0,38.0`)
- **GeoJSON geometry**: paste the geometry object directly
- **No spatial coverage**: type `none` (only for genuinely unlocated data)

Also answer:

- What is the native CRS? (e.g., EPSG:4326, EPSG:32654, WKT string)
- Do you want `proj` extension fields in the output? (yes / no)

---

**Q5 — Temporal coverage**

Provide the date/time information. Accepted formats:

1. Single datetime: ISO 8601 string (e.g., `2024-06-15T10:30:00Z`)
2. Date range: start and end as ISO 8601 strings
3. Date only (no time): e.g., `2024-06-15`
4. No temporal information: type `none`

---

**Q6 — Assets**

List each asset file, one per line, using the format:

```
filename_or_url | media_type | role(s)
```

Example:

```
s3://my-bucket/data/scene_B04.tif | image/tiff; application=geotiff; profile=cloud-optimized | data
s3://my-bucket/data/scene_thumbnail.jpg | image/jpeg | thumbnail, overview
s3://my-bucket/metadata/scene.xml | application/xml | metadata
```

Standard roles: `data`, `metadata`, `thumbnail`, `overview`, `visual`, `index`, `date`, `rendered`

If you do not yet have real URLs, use placeholder paths like `s3://BUCKET/PREFIX/FILENAME.tif` — the generated output will annotate them with `# TODO: replace with real URL`.

---

**Q7 — Common extensions**

Which STAC extensions should be applied? Based on your data type, auto-suggestions are shown below. Type the numbers you want, type `auto` to accept all suggestions, or type `none` to skip.

Auto-suggested based on data type from Q2:

- Optical / multispectral → `eo`, `view`
- SAR → `sar`
- LiDAR / DEM → `raster`
- Zarr / datacube → `datacube`
- ML model → `ml-model`
- ML labels → `label`

Additional commonly used extensions:

1. `eo` — Electro-optical band metadata
2. `view` — Sun/satellite viewing geometry
3. `sar` — Synthetic Aperture Radar fields
4. `raster` — Raster band statistics and data types
5. `proj` — CRS and projection metadata
6. `datacube` — N-dimensional datacube dimensions/variables
7. `ml-model` — Trained ML model metadata
8. `label` — ML training dataset labels
9. `timestamps` — Published/expires/unpublished lifecycle dates
10. `version` — Catalog object versioning
11. `scientific` — DOI and citation metadata

---

> **Esoteric extensions menu** — present this after the user responds to Q7, before asking Q8.

```
Are any of these specialised extensions relevant to your data?
Type the numbers that apply (comma-separated), or "none" / "done" to skip.

Group A — Grid & Spatial Indexing
  1. mgrs       — Military Grid Reference System tile codes (e.g., Sentinel-2 grid tiles)
  2. grid       — Generic grid code field (WRS2, MGRS, MODIS, etc.) for aggregation/search

Group B — Imagery Specialisation
  3. classification     — Categorical pixel values / bitfields (cloud masks, land cover, segmentation masks)
  4. hsi                — Hyperspectral imagery wavelength min/max
  5. card4l / ceos-ard  — CEOS Analysis Ready Data compliance documentation
  6. perspective-imagery — Non-photogrammetric camera imagery (phones, SLRs)
  7. stereo-imagery     — Stereo/tri-stereo capture metadata for 3D reconstruction

Group C — Data Access & Storage
  8. alternate-assets   — Multiple access paths for the same asset (S3 + GCS + HTTP)
  9. file               — Checksums, file sizes, byte offsets for integrity verification
 10. storage            — Cloud storage relationship metadata
 11. authentication     — OAuth/API key auth flows for secured assets
 12. tiled-assets       — Template URLs for tile pyramid assets
 13. link-templates     — Templated links with replaceable variables (Zarr chunks, XYZ tiles)

Group D — Scientific & Quality
 14. scientific    — DOI and formal citation metadata
 15. accuracy      — Positional/attribute accuracy measurements
 16. cmip6         — Climate Model Intercomparison Project Phase 6 metadata
 17. contacts      — Detailed provider contact information
 18. themes        — Controlled vocabulary keywords (Geonames, etc.)
 19. language      — Multi-lingual metadata support

Group E — Machine Learning
 20. ml-model      — Trained model artifact metadata
 21. label         — ML training dataset labels
 22. trainingdml-ai — AI training dataset documentation

Group F — Archive & Special
 23. archive        — Data bundled in ZIP/TAR archives
 24. composite      — Virtual assets composed from multiple source assets
 25. solar-system   — Extra-terrestrial / planetary imagery
```

---

**Q8 — Deployment target**

Where will this STAC object be deployed or served?

1. Static object storage (S3, GCS, Azure Blob) — files on a bucket
2. stac-fastapi (API server)
3. pgSTAC (PostgreSQL-backed STAC API)
4. Local / development only
5. Unknown / not yet decided

---

**Q9 — Output format**

What output would you like?

1. STAC JSON only
2. stactools Python script only
3. Both JSON and Python (default)
4. rio-stac CLI command
5. xstac (for Zarr / xarray datasets)

---

## Phase 2: Pre-Generation Confirmation

Before generating output, present a confirmation summary table:

```
┌─────────────────────┬──────────────────────────────────────────────────────────┐
│ Field               │ Value                                                    │
├─────────────────────┼──────────────────────────────────────────────────────────┤
│ Object type         │ [Item / Collection / Catalog / Full hierarchy]           │
│ Data type           │ [optical / SAR / LiDAR / DEM / vector / Zarr / ML / …]  │
│ Sensor / source     │ [Sentinel-2 / custom / …]                               │
│ Spatial             │ [bbox: W,S,E,N] [CRS: EPSG:xxxx] [proj: yes/no]         │
│ Temporal            │ [datetime / range / none]                                │
│ Assets              │ [count] assets listed                                    │
│ Extensions          │ [comma-separated list]                                   │
│ Deployment target   │ [static S3 / stac-fastapi / pgSTAC / local / unknown]   │
│ Output format       │ [JSON / Python / both / rio-stac / xstac]               │
└─────────────────────┴──────────────────────────────────────────────────────────┘
Does this look correct? Reply "yes" to generate, or tell me what to correct.
```

Do not proceed to Phase 3 until the user confirms.

## Phase 3: Generate STAC Output

Generate output blocks in this order:

1. **Setup** — virtual environment creation and dependency installation
2. **STAC JSON** — complete and valid, with placeholder comments for real URLs
3. **stactools Python script** — full runnable module (if requested)
4. **Validation commands** — `stac validate` CLI
5. **Next steps checklist** — per deployment target

### Extension Auto-Application Rules

Apply extensions automatically based on data type — do not ask:

| Data type | Auto-apply extensions |
|---|---|
| Optical / multispectral | `eo`, `view` |
| SAR | `sar` |
| LiDAR / DEM | `raster` |
| Zarr / datacube | `datacube` |
| ML model | `ml-model` |
| ML labels | `label` |

Every auto-applied extension must have its full schema URI listed in `stac_extensions`.

### Known Sensor Pre-fills

Populate the following fields automatically when the sensor is known — do not ask for them:

**Sentinel-2:**

```json
"platform": "sentinel-2b",
"constellation": "sentinel-2",
"instruments": ["msi"],
"gsd": 10,
"eo:bands": [
  {"name": "B01", "common_name": "coastal", "center_wavelength": 0.4427, "full_width_half_max": 0.021},
  {"name": "B02", "common_name": "blue",    "center_wavelength": 0.4924, "full_width_half_max": 0.066},
  {"name": "B03", "common_name": "green",   "center_wavelength": 0.5598, "full_width_half_max": 0.036},
  {"name": "B04", "common_name": "red",     "center_wavelength": 0.6646, "full_width_half_max": 0.031},
  {"name": "B05", "common_name": "rededge", "center_wavelength": 0.7041, "full_width_half_max": 0.015},
  {"name": "B06", "common_name": "rededge", "center_wavelength": 0.7405, "full_width_half_max": 0.015},
  {"name": "B07", "common_name": "rededge", "center_wavelength": 0.7828, "full_width_half_max": 0.020},
  {"name": "B08", "common_name": "nir",     "center_wavelength": 0.8328, "full_width_half_max": 0.106},
  {"name": "B8A", "common_name": "nir08",   "center_wavelength": 0.8647, "full_width_half_max": 0.021},
  {"name": "B09", "common_name": "nir09",   "center_wavelength": 0.9451, "full_width_half_max": 0.020},
  {"name": "B11", "common_name": "swir16",  "center_wavelength": 1.6137, "full_width_half_max": 0.091},
  {"name": "B12", "common_name": "swir22",  "center_wavelength": 2.2024, "full_width_half_max": 0.175}
]
```

Recommend `stactools-sentinel2` package and `stactools.sentinel2.stac.create_item()` for sensor-specific creation.

**Sentinel-1:**

```json
"platform": "sentinel-1",
"constellation": "sentinel-1",
"instruments": ["c-sar"],
"sar:frequency_band": "C",
"sar:center_frequency": 5.405,
"sar:polarizations": ["VV", "VH"]
```

Recommend `stactools-sentinel1` package.

**Landsat-8 / Landsat-9:**

```json
"gsd": 30,
"instruments": ["oli", "tirs"],
"eo:bands": [
  {"name": "B1",  "common_name": "coastal",  "center_wavelength": 0.443},
  {"name": "B2",  "common_name": "blue",     "center_wavelength": 0.482},
  {"name": "B3",  "common_name": "green",    "center_wavelength": 0.562},
  {"name": "B4",  "common_name": "red",      "center_wavelength": 0.655},
  {"name": "B5",  "common_name": "nir",      "center_wavelength": 0.865},
  {"name": "B6",  "common_name": "swir16",   "center_wavelength": 1.609},
  {"name": "B7",  "common_name": "swir22",   "center_wavelength": 2.201},
  {"name": "B8",  "common_name": "pan",      "center_wavelength": 0.590},
  {"name": "B9",  "common_name": "cirrus",   "center_wavelength": 1.374},
  {"name": "B10", "common_name": "lwir11",   "center_wavelength": 10.895},
  {"name": "B11", "common_name": "lwir12",   "center_wavelength": 12.005}
]
```

Recommend `stactools-landsat` package.

### Pre-Output Validation Checklist

Check each of the following silently before presenting output. Fix violations automatically rather than asking the user:

- [ ] `stac_version` is `"1.0.0"`
- [ ] `id` contains only alphanumerics, hyphens, or underscores — no colons, slashes, or spaces
- [ ] `bbox` is present when `geometry` is not null
- [ ] `datetime: null` is paired with both `start_datetime` and `end_datetime`
- [ ] Every extension field used has its schema URI in `stac_extensions`
- [ ] Uses `proj:code` not `proj:epsg` (deprecated since proj extension v1.1.0)
- [ ] COG assets use `image/tiff; application=geotiff; profile=cloud-optimized`
- [ ] Collections have `extent`, `license`, and `summaries`
- [ ] Catalogs do not have `extent`, `license`, or `summaries`
- [ ] Link `href` values use relative paths for static catalogs, absolute URLs for API / pgSTAC deployments

### STAC JSON Templates

#### Item

```json
{
  "type": "Feature",
  "stac_version": "1.0.0",
  "stac_extensions": [
    "https://stac-extensions.github.io/eo/v1.1.0/schema.json",
    "https://stac-extensions.github.io/view/v1.0.0/schema.json"
  ],
  "id": "my-item-id",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[W, S], [E, S], [E, N], [W, N], [W, S]]]
  },
  "bbox": [W, S, E, N],
  "properties": {
    "datetime": "2024-06-15T10:30:00Z",
    "platform": "PLATFORM",
    "instruments": ["INSTRUMENT"],
    "gsd": 10,
    "eo:cloud_cover": 5.2,
    "view:sun_azimuth": 148.2,
    "view:sun_elevation": 62.1
  },
  "links": [
    {"rel": "self",       "href": "./my-item-id.json",      "type": "application/geo+json"},
    {"rel": "root",       "href": "../catalog.json",        "type": "application/json"},
    {"rel": "parent",     "href": "../collection.json",     "type": "application/json"},
    {"rel": "collection", "href": "../collection.json",     "type": "application/json"}
  ],
  "assets": {
    "data": {
      "href": "s3://BUCKET/PREFIX/scene.tif",
      "type": "image/tiff; application=geotiff; profile=cloud-optimized",
      "roles": ["data"],
      "title": "Data asset"
    },
    "thumbnail": {
      "href": "s3://BUCKET/PREFIX/thumbnail.jpg",
      "type": "image/jpeg",
      "roles": ["thumbnail"]
    }
  },
  "collection": "my-collection-id"
}
```

#### Collection

```json
{
  "type": "Collection",
  "stac_version": "1.0.0",
  "stac_extensions": [],
  "id": "my-collection-id",
  "title": "My Collection",
  "description": "Description of the collection.",
  "license": "proprietary",
  "extent": {
    "spatial":  {"bbox": [[W, S, E, N]]},
    "temporal": {"interval": [["2024-01-01T00:00:00Z", null]]}
  },
  "summaries": {
    "platform":    ["PLATFORM"],
    "instruments": ["INSTRUMENT"],
    "gsd":         {"minimum": 10, "maximum": 10}
  },
  "providers": [
    {
      "name":  "Provider Name",
      "roles": ["producer", "licensor"],
      "url":   "https://example.com"
    }
  ],
  "links": [
    {"rel": "self",   "href": "./collection.json",          "type": "application/json"},
    {"rel": "root",   "href": "../catalog.json",            "type": "application/json"},
    {"rel": "parent", "href": "../catalog.json",            "type": "application/json"},
    {"rel": "items",  "href": "./items/",                   "type": "application/geo+json"}
  ]
}
```

#### Catalog

```json
{
  "type": "Catalog",
  "stac_version": "1.0.0",
  "id": "my-catalog-id",
  "title": "My Catalog",
  "description": "Root catalog description.",
  "links": [
    {"rel": "self",  "href": "./catalog.json",                     "type": "application/json"},
    {"rel": "root",  "href": "./catalog.json",                     "type": "application/json"},
    {"rel": "child", "href": "./my-collection/collection.json",    "type": "application/json"}
  ]
}
```

### stactools Code Template

Output begins with the setup block, then the Python script.

**Setup:**

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Core installation
pip install 'stactools[validate]'

# Sensor-specific package (if applicable, e.g. Sentinel-2):
pip install stactools-sentinel2

# For raster-based item creation:
pip install rio-stac

# For Zarr / xarray:
pip install xstac
```

**Python script:**

```python
#!/usr/bin/env python3
"""
Create and validate a STAC Item/Collection/Catalog using stactools.
Generated by /create-stac.
"""

import pystac
from datetime import datetime, timezone
from stactools.core.validate import validate


# ── Item creation ──────────────────────────────────────────────────────────────

def create_item() -> pystac.Item:
    item = pystac.Item(
        id="my-item-id",
        geometry={
            "type": "Polygon",
            "coordinates": [[[W, S], [E, S], [E, N], [W, N], [W, S]]],
        },
        bbox=[W, S, E, N],
        datetime=datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc),
        properties={
            "platform": "PLATFORM",
            "instruments": ["INSTRUMENT"],
            "gsd": 10,
        },
        stac_extensions=[
            "https://stac-extensions.github.io/eo/v1.1.0/schema.json",
            "https://stac-extensions.github.io/view/v1.0.0/schema.json",
        ],
    )

    # Add assets
    item.add_asset(
        "data",
        pystac.Asset(
            href="s3://BUCKET/PREFIX/scene.tif",  # TODO: replace with real URL
            media_type="image/tiff; application=geotiff; profile=cloud-optimized",
            roles=["data"],
            title="Data asset",
        ),
    )
    item.add_asset(
        "thumbnail",
        pystac.Asset(
            href="s3://BUCKET/PREFIX/thumbnail.jpg",  # TODO: replace with real URL
            media_type="image/jpeg",
            roles=["thumbnail"],
        ),
    )

    item.add_link(pystac.Link("collection", "../collection.json"))
    item.add_link(pystac.Link("root",       "../catalog.json"))

    return item


# ── Collection creation ────────────────────────────────────────────────────────

def create_collection() -> pystac.Collection:
    spatial_extent  = pystac.SpatialExtent(bboxes=[[W, S, E, N]])
    temporal_extent = pystac.TemporalExtent(
        intervals=[[datetime(2024, 1, 1, tzinfo=timezone.utc), None]]
    )
    collection = pystac.Collection(
        id="my-collection-id",
        description="Description of the collection.",
        extent=pystac.Extent(spatial=spatial_extent, temporal=temporal_extent),
        license="proprietary",
        title="My Collection",
    )
    return collection


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    item       = create_item()
    collection = create_collection()

    collection.add_item(item)

    # Validate before writing
    validate(item)
    validate(collection)
    print("✅ Validation passed")

    # Build catalog and write to disk
    catalog = pystac.Catalog(id="my-catalog-id", description="Root catalog")
    catalog.add_child(collection)
    catalog.normalize_hrefs("./stac-output")
    catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)
    print("✅ STAC written to ./stac-output/")
```

### Validation Steps

```bash
# Validate a single Item
stac validate path/to/item.json

# Validate a Collection
stac validate path/to/collection.json

# Validate recursively from a Catalog root
stac validate path/to/catalog.json --recursive

# In-Python validation
from stactools.core.validate import validate
validate(item)  # raises exception if invalid
```

### Next Steps by Deployment Target

**Static S3 / GCS / Azure Blob:**

- [ ] Replace all placeholder `s3://BUCKET/PREFIX/` hrefs with real signed or public URLs
- [ ] Run `stac validate` on each object before upload
- [ ] Upload STAC JSON files alongside data assets, mirroring the prefix structure
- [ ] Set `Content-Type: application/geo+json` on Item files, `application/json` on Collection/Catalog files
- [ ] Enable CORS on the bucket if STAC Browser access is needed

**stac-fastapi:**

- [ ] Set all `href` values to absolute URLs pointing to your API base URL
- [ ] Ingest items using `pypgstac load` or `pystac-client`
- [ ] Confirm `GET /conformance` lists the correct conformance classes
- [ ] Set `Access-Control-Allow-Origin: *` in API middleware for browser-based tools

**pgSTAC:**

- [ ] Install `pypgstac`: `pip install pypgstac`
- [ ] Load collection: `pypgstac load collections collection.json`
- [ ] Load items: `pypgstac load items item.json`
- [ ] Confirm spatial and temporal indexes are in place on the pgSTAC schema

**Local / development:**

- [ ] Run `stac validate path/to/item.json` to confirm spec compliance
- [ ] Open in STAC Browser (browser-based): drag-and-drop the `catalog.json`
- [ ] Query locally: `pystac_client.Client.from_file("./stac-output/catalog.json")`

**Unknown / not yet decided:**

- [ ] Keep all `href` values as relative paths for maximum portability
- [ ] Run `stac validate path/to/item.json` now to catch issues early
- [ ] Consult the Sparkgeo Cloud-Native Geospatial Handbook for deployment guidance
