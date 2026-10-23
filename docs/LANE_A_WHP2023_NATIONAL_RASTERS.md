# Lane A — complete original USDA WHP2023 270m GeoTIFF source-ingestion handoff

## Verified scope and real-source results, October 23, 2026

Independent end-to-end official U.S. Forest Service archive download + **six original real GeoTIFFs** + all-source-grid-cell census + class/mask + SHA-256 validation passed in [Actions run 40007893600](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40007893600) (first successful validation; additional QA/tests/re-sampling runs listed in the dedicated PR).

**Original publication**: Dillon, Gregory K. 2023, Wildfire Hazard Potential for the United States (270-m), version 2023, 4th edition, updated July 17, 2024. DOI https://doi.org/10.2737/RDS-2015-0047-4. Publisher's metadata: https://research.fs.usda.gov/firelab/products/dataandtools/wildfire-hazard-potential . Dataset reports landscape largely from 2020, and is **NOT wildfire occurrence, current-season forecast, calibrated loss probability, damage, insurance coverage or insured property score**. Classes are relative **landscape** hazard; Alaska and CONUS classes can have different domain-relative context.

**Official first-party original source URL** (DO NOT substitute a third-party mirror):
https://www.fs.usda.gov/rds/archive/products/RDS-2015-0047-4/RDS-2015-0047-4_Data.zip

- Original downloaded bytes **368,424,961** (real full HTTP 200, not a HEAD-count substitute).
- Original ZIP independently SHA-256 verified **`7f10f1f8dd97551b8be1458fe0ec924df60b2cea7ece2d1af4c3c1166d1895ab`**.
- Exactly **6** real GeoTIFFs: `whp2023_{cls,cnt}_{conus,ak,hi}.tif`. Extract only these; retain untouched original publisher ZIP, its content SHA and each original GeoTIFF bytes/CRC/SHA.
- Source CRS and resolution confirmed **CONUS EPSG:5070 270×270 native metres**, **Alaska EPSG:3338 270×270 metres**, **Hawaii ESRI:102007 270×270 metres**. Keep original CRS/native rows and columns. Beware Rasterio `dataset.index(x,y)` returns **(row,column)**, not the reverse; this error was discovered and regression-fixed before final source-point proof.
- Original nodata: classified **255**, continuous **2147483647**. Continuous valid cell value **0** is a valid nonnegative modeled value, **NOT** a missing pixel and **NOT** zero modeled insurance risk.
- Classified numeric codes: **1 Very Low, 2 Low, 3 Moderate, 4 High, 5 Very High, 6 Non-burnable, 7 Water**. Codes 6 and 7 remain masks/land-cover conditions, not low wildfire risk.

### Actual full-source pixel census

Each pair of classified and continuous TIFFs covers the same publisher domain. Numbers below are **per raster product**; do not add classified + continuous as independent geographic pixels.

| Source publisher domain | TIFF grid (columns × rows) | Valid original classified pixels | Original masked/no-data pixels | Classified 4/5 high+very-high pixels |
|---|---|---:|---:|---:|
| CONUS | 17,372 × 11,283 | **110,817,217** | **85,191,059** | **13,463,839** |
| Alaska | 13,846 × 7,430 | **22,337,483** | **80,538,297** | **1,966,199** |
| Hawaii | 2,266 × 1,401 | **350,315** | **2,824,351** | **11,522** |
| **Three domains** | | **133,505,015** | **168,553,707** | **15,441,560** |

Original classified valid pixels across all domains, by publisher code: **1=41,668,377; 2=23,299,629; 3=17,745,744; 4=11,220,017; 5=4,221,543; 6=26,392,217; 7=8,957,488**. No negative fabricated values; masks remain separate. A valid **133.5M publisher landscape cells is not 133.5M buildings or insured properties.**

The full source raster ingestion in a temporary GitHub Actions runner is a substantial improvement over the previous **70 + 70 sampled ImageServer pixels** and **35,304 source publisher geographic aggregates**. Those two earlier cohorts remain separate and must not be summed into this spatial cell census. Exact full original source bytes and first-party citation are included in the emitted machine-readable manifest. The public USDA publication indicates reuse without permission/fees with requested attribution and model limitations; retain the citation in derivative interfaces.

## Reproducible private installation

Requires Python 3.12+, NumPy, rasterio, approximately 3–5 GB temporary disk headroom and additional permanent space for original ZIP plus six extracted immutable TIFFs. The importer uses **only the pinned original official URL**, SHA-256, ZIP member path/bounds guard, CRS/shape validation, all-block TIFF mask counts, original category census and independent SHA for all six products. Production activation is content-addressed and atomic; a failed original checksum or a tampered existing release cannot alter `current.json`.

```bash
python -m pip install 'rasterio>=1.4,<2' 'numpy>=1.26,<3'
python -m scripts.lane_a_whp_full_raster \
  --root /srv/facility-risk/source-index/whp2023-full \
  --expected-sha256 7f10f1f8dd97551b8be1458fe0ec924df60b2cea7ece2d1af4c3c1166d1895ab \
  --full-audit
```

Or supply a separately downloaded original archive via `--source-zip /authorized/private/original.zip` (same expected SHA). The output is `releases/<SHA-derived-id>/{manifest.json,RDS-2015-0047-4_Data.zip,source-tiffs/*.tif}` plus atomic `current.json`; the files are set read-only at installation. Source ZIP archive URL/version/size/sha and individual TIFFs' SHA, CRS, nodata, pixel counts, sample point values and category histogram are recorded. The importer is idempotent when the content SHA is identical and retains the previously validated release on errors. Do **not** use GitHub Actions ephemeral storage as the private permanent source host.

The matching read-only caller `facilityrisk/lane_a_national_whp.py` checks original ZIP SHA against the hard-pinned observed 2023 publication version, 6 independent original source TIFF hashes, cell/mask counts and source CRS evidence on load. It requires an existing **currently corroborated site coordinate** in the private workspace for property-context queries; source observations never auto-merge regulatory identities or facilities. A coordinate outside valid pixels returns **UNKNOWN**, class 6/7 is a mask, and the returned values are not claims, probabilities, losses or insured payouts.

## Operational blockers, not falsely resolved

The raster has been **downloaded, accepted, full-pixel validated, locally queried and installed in temporary Actions QA**. A secure, durable private host, local volume encryption/backups, permanent source data retention, browser integration to the real authenticated host, tenant segregation, actual real-property site review, current wildfire forecasts, and insured loss outcomes remain unverified. **Production-host deployed=0 until explicitly verified** under [Issue #39](https://github.com/jhennessy-pharm3r/FacilityTest/issues/39). Whole national FEMA NFHL source geometry (5.8M publisher count-only features) is a **separate** unresolved source (34 validated bounded QA polygons installed) and is not magically fixed by WHP ingestion.
