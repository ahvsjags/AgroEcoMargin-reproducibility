# AgroEcoMargin reproducibility archive, release v1.0.7

## Scope

This archive supports the manuscript *Seasonal heat and dryness are associated with lower marginal nitrogen responses in a long-term field experiment*.

It contains only processed analytical products, figure-source data, analysis scripts, export-ready figures and an environment specification. It does **not** redistribute provider-controlled source files.

## Contents

- `code/`: scripts for treatment-rate recovery, RGE inference, irrigation contrast, remote-sensing linkage and validation, figure generation, submission diagnostics, and Crossref reference verification.
- `source_data/`: CSV values used for all main and supplementary figure panels.
- `analysis_outputs/`: crop-year support, leave-two-year-out estimates and complete outer-year satellite predictions, metrics and selected ridge penalties.
- `figures/`: 600 dpi RGB PNG and TIFF versions of every main and supplementary figure.
- `manuscript/`: submission source text, supporting source text, bibliography and pinned package requirements.

## Reproduction order

1. Create a Python environment from `manuscript/requirements_v7_1_20260710.txt`.
2. Obtain public KBS LTER KBS033-001 yield data and KBS station weather data from the catalog cited in the manuscript.
3. Place those provider files in the paths configured in scripts `101` and `102`, or set the documented project path environment variables.
4. Run scripts `101`, `104`, `105`, `106`, and `107` in numerical order. Script `108` verifies bibliographic metadata through the Crossref API.
5. Compare regenerated source-data CSVs against `source_data/`.

## Data provenance and restrictions

The KBS LTER public agronomic yield and weather tables remain available from the KBS LTER Data Catalog. This archive includes processed results derived from the cited public records. It does not include controlled data, credentials, or third-party imagery products that are not licensed for redistribution.

## Public repository

The public reproducibility repository for this release is https://github.com/ahvsjags/AgroEcoMargin-reproducibility/releases/tag/v1.0.7. The repository contains the code, processed analytical products, source-data CSVs, PNG figure assets, documentation, an MIT license for original code and documentation, and the pinned environment required to reproduce the reported analyses. Large TIFF delivery files remain in the local submission package and are available upon editorial request.

