# Supporting Information

**Seasonal heat and dryness are associated with lower marginal nitrogen responses in a long-term field experiment**

This Supporting Information provides the data-linkage, model and validation details for the main manuscript.

## Supplementary Methods 1. Study records, variables and analytical inclusion

The primary agronomic source was the public KBS LTER Resource Gradient Experiment (RGE) agronomic-yield table, KBS033-001. The RGE source records plot, treatment, replicate, irrigation status, crop, harvest year, fertilizer rate and yield. Annual weather summaries were joined by harvest year. Rainfed response models retained a record only when `yield_kg_ha`, recovered `n100`, `plot`, `year`, `heat_dry_stress_z` and `crop_group` were all observed. This yielded 1,005 records from 76 plots and 27 years (1999--2025). The irrigation contrast used the same required fields and only years represented by both irrigation states, yielding 1,674 records from 72 plots and 23 years (2003--2025).

No values were imputed for yield, crop, plot, harvest year or weather in the RGE analyses. Of 1,016 rainfed source records, 11 had no yield value and were excluded; no other primary-panel field was missing after deterministic recovery of documented fertilizer rates. Crop group was deterministically assigned from the crop name: *Zea* to corn, *Glycine* to soybean and *Triticum* to wheat. Yield was kept in the provider-reported crop-specific standard-moisture unit of kg ha⁻¹. Nitrogen was divided by 100 before model fitting (`n100`), so every reported slope coefficient is kg ha⁻¹ per 100 kg N ha⁻¹.

### Table S1. Analysis variables and provenance

| Variable | Analysis use | Unit or coding | Source and transformation |
|---|---|---|---|
| `yield_kg_ha` | Outcome | kg ha⁻¹ | Observed public RGE agronomic-yield record |
| `fertilizer_rate_kg_ha` | Treatment | kg N ha⁻¹ | Reported value or deterministic F1–F9 recovery described in Supplementary Methods 2 |
| `n100` | Model treatment scale | 100 kg N ha⁻¹ | `fertilizer_rate_kg_ha / 100` |
| `plot`, `year` | Fixed effects and resampling blocks | Identifier | Public RGE record |
| `crop_group` | Crop-specific nitrogen slopes | corn, soybean or wheat | Deterministic map from public crop name |
| `irrigated_binary` | Irrigation contrast | 0 rainfed, 1 irrigated | Public RGE irrigation field |
| `heat_days_30c_gs` | Heat component | days | KBS annual station summary, 1 April--31 October |
| `dry_days_lt1mm_gs` | Dryness component | days | KBS annual station summary, 1 April--31 October |
| `heat_dry_stress_z` | Primary exposure | standardized index | Equal-weight sum of the two standardized components divided by √2 |
| `time_c` | Slope-trend adjustment | decades, centered | `(year - mean(year)) / 10` |

## Supplementary Methods 2. Deterministic treatment-rate recovery

The public RGE yield file preserves the F1–F9 treatment identifier when later fertilizer-rate cells are blank. We reconstructed a blank rate only from the published crop-specific treatment schedule. Before any replacement, the schedule was compared with all 1,412 non-missing public rate entries and had exact agreement. Recovery used the treatment identifier and the locked schedule only. In the rainfed primary panel, 789 records retained a provider-reported rate and 216 had a rate recovered from the schedule. The recovery script raises an error if a non-missing provider value disagrees with the schedule.

### Table S2. Documented F1–F9 nitrogen schedule (kg N ha⁻¹)

| Treatment | Corn | Wheat | Soybean, usual years | Soybean, 2012 only |
|---|---:|---:|---:|---:|
| F1 | 0 | 0 | 0 | 0 |
| F2 | 34 | 22 | 0 | 17 |
| F3 | 67 | 45 | 0 | 34 |
| F4 | 101 | 67 | 0 | 50 |
| F5 | 134 | 90 | 0 | 67 |
| F6 | 168 | 112 | 0 | 84 |
| F7 | 202 | 134 | 0 | 101 |
| F8 | 246 | 157 | 0 | 123 |
| F9 | 291 | 179 | 0 | 146 |

## Supplementary Methods 3. Season-level weather exposure

KBS weather data were aggregated over 1 April–31 October for each harvest year. The heat component was the number of growing-season days above 30 °C. The dryness component was the number of growing-season days with precipitation below 1 mm. Each component was standardized across the years available to the relevant analytical panel using the population standard deviation. The primary index was `(heat_z + dry_z) / √2`. Heat-only and dry-day-only models were prespecified component sensitivity analyses; they do not constitute separate outcomes or a search for the strongest threshold. Because every eligible record within a year shares the same weather index, year is the resampling and permutation unit.

## Supplementary Methods 4. Nitrogen-response and irrigation models

For rainfed plots, the fitted model was:

\[
Y_{ipt} = \alpha_p + \gamma_t + \delta_cN_{ipt} + \beta N_{ipt}S_t + \tau N_{ipt}T_t + \varepsilon_{ipt}.
\]

Here, *Y* is yield; *p*, *t* and *c* index plot, year and crop group; *N* is nitrogen in 100 kg N ha⁻¹ units; *S* is the standardized heat-dry index; and *T* is centered time in decades. `C(year)` and `C(plot)` implement fixed effects, and `C(crop_group):n100` implements crop-specific nitrogen slopes. One crop group is observed in each harvest year, so crop intercepts are perfectly collinear with year fixed effects and are not separately estimable. The estimand *beta* is the change in the marginal nitrogen response for a one-standard-deviation increase in the heat-dry index.

The concurrent irrigation model was estimated for 2003--2025 and added nitrogen-by-irrigation and nitrogen-by-heat-dry-by-irrigation terms to the same fixed-effect structure. The three-way coefficient is the irrigated-minus-rainfed difference in the heat-dry nitrogen response and is interpreted as an irrigation contrast, not as a direct manipulation of weather.

Conventional model intervals used covariance clustered by harvest year. The rainfed model was additionally refit after excluding each year and after excluding every pair of years (351 deterministic combinations). Complete-year resampling used 240 draws for the rainfed model and 300 draws for the irrigation model. A bootstrap draw retained every eligible record within each sampled year, created a bootstrap-year fixed effect for repeated draws, and refit the prespecified formula. For each of 600 permutations, the observed one-per-year stress values were reassigned across years while all plot-level records and model terms remained fixed. Random seed was 20260710.

### Table S3. Primary estimates and independent weather support

| Analysis | Rows | Years | Plots | Estimate (kg ha⁻¹ per 100 kg N per SD) | Year-clustered 95% CI | Annual diagnostic |
|---|---:|---:|---:|---:|---|---|
| Rainfed N x heat-dry | 1,005 | 27 | 76 | -254.6 | -393.0, -116.2 | Bootstrap: -546.0, 323.4; permutation P = 0.236 |
| Rainfed N x heat | 1,005 | 27 | 76 | -250.2 | -400.4, -100.0 | Component sensitivity |
| Rainfed N x dry days | 1,005 | 27 | 76 | -301.4 | -586.2, -16.6 | Component sensitivity |
| Concurrent rainfed N x heat-dry | 1,674 | 23 | 72 | -368.7 | -643.3, -94.1 | Concurrent 2003--2025 seasons |
| Irrigation x nitrogen x heat-dry interaction | 1,674 | 23 | 72 | +443.4 | 263.9, 622.9 | Bootstrap: -221.5, 606.5; permutation P = 0.098 |

### Table S6. Crop-year support and coefficient identification

| Crop group | Harvest years | Rainfed records | Maximum plots in one crop-year | Nitrogen-rate support | Identification note |
|---|---:|---:|---:|---|---|
| Corn | 13 | 505 | 67 | 0–291 kg N ha⁻¹, nine rates | Crop intercept absorbed by year fixed effect; crop-specific N slope estimated |
| Soybean | 7 | 252 | 36 | Unfertilized except nine-rate 2012 gradient | Crop intercept absorbed by year fixed effect; crop-specific N slope estimated |
| Wheat | 7 | 248 | 36 | 0–179 kg N ha⁻¹, nine rates | Crop intercept absorbed by year fixed effect; crop-specific N slope estimated |

The 351 leave-two-year-out estimates ranged from −356.9 to −162.4 kg ha⁻¹ per 100 kg N per standard deviation of heat-dry stress, and were all negative. Full crop-year coverage and the coefficient distribution are shown in Figure S8.

## Supplementary Methods 5. Plot-level satellite-yield linkage

The satellite analysis used observed MCSE Treatment x Replicate harvest records. Each yield record was linked to a documented Treatment x Replicate plot crosswalk. For an observed harvest date, the final usable temporal bin was the 24-step calendar half-month immediately preceding the harvest half-month; feature trajectories therefore ended before harvest.

KBS Landsat and Sentinel-2 Gold cubes supply six reflectance bands (blue, green, red, nir08, swir16 and swir22), `valid_mask`, `clear_fraction`, `obs_count`, `time_gap_days`, `plot_mask` and `plot_id_mask`. Features were summarized only from pixels with the matching positive plot identifier and valid spectral data. For each sensor and plot-year we calculated mean, maximum and final values for reflectance bands, NDVI, NDWI, NBR, clear fraction, observation count, valid fraction, time gap and pixel count. NDVI slope was calculated when at least two valid preharvest bins were available.

The image-level and phenology-slot quality checks, including clear fraction, observation count, QA mode, time-gap support and plot support, are shown in Figure S10.

The feature builder generated 876 observed MCSE harvest records with a matching plot geometry, including 830 records with at least one preharvest Landsat feature and 216 with Sentinel-2 coverage. Plot-level summaries were paired with the observed crop-only yield outcome. Normalized difference vegetation index (NDVI), normalized difference water index (NDWI) and normalized burn ratio (NBR) are calculated from the same harvest-truncated band series.

## Supplementary Methods 6. Nested temporal prediction evaluation

The management-only comparator used categorical crop group, treatment and replicate. The Landsat feature block consisted of NDVI mean, maximum, final value and slope; NDWI mean; NBR mean; red, nir08, swir16 and swir22 means; and clear-fraction, observation-count, valid-fraction and time-gap means. Each outer fold held out one entire calendar year. Within the remaining years only, categorical variables were one-hot encoded with unknown categories ignored, numeric variables were median-imputed and standardized, and ridge penalty alpha was chosen by GroupKFold grouped by year. The candidate alpha values were 0.1, 1, 10, 100 and 1,000; the number of inner folds was the smaller of five and the number of available training years.

Outer-fold predictions were pooled to calculate root-mean-square error (RMSE), mean absolute error (MAE) and R2. The main text reports RMSE. A 5,000-draw year-block bootstrap recalculated the difference in mean squared error (MSE) between management-only and management-plus-Landsat predictions. To document the full validation process, Figure S9 reports all 37 outer-year RMSE values, outer-fold prediction-versus-observation plots and the ridge penalty selected exclusively within each training set. This procedure assesses the stability of the incremental feature block under calendar-year resampling; it does not create an independent-site validation.

### Table S4. Strict temporal satellite-yield validation

| Evaluation subset | Model | Observations | Outer evaluation | RMSE (kg ha⁻¹) |
|---|---|---:|---|---:|
| 1989--2025 Landsat | Management only | 830 | Leave one calendar year out | 1,821.5 |
| 1989--2025 Landsat | Management + plot Landsat | 830 | Leave one calendar year out | 1,874.8 |
| 2017--2023 matched dual-sensor | Management only | 216 | Leave one calendar year out | 1,674.9 |
| 2017--2023 matched dual-sensor | Management + Landsat | 216 | Leave one calendar year out | 2,276.0 |
| 2017--2023 matched dual-sensor | Management + Sentinel-2 | 216 | Leave one calendar year out | 2,182.2 |
| 2017--2023 matched dual-sensor | Management + both sensors | 216 | Leave one calendar year out | 2,845.3 |

## Supplementary Methods 7. Software, scripts and source-data index

All analyses were run in Python using the pinned environment in `requirements_v7_1_20260710.txt`: numpy 2.3.5, pandas 2.3.3, matplotlib 3.10.8, scipy 1.16.0, statsmodels 0.14.6 and scikit-learn 1.8.0. Randomized analyses used seed 20260710. The public reproducibility archive contains the processed tables that underlie each panel, the bootstrap and permutation draws, and source CSVs for all figures. Provider-controlled raw data are identified by catalog accession and access condition rather than redistributed.

### Table S5. Reproducibility map

| Component | Primary script | Key output or source-data product | Role |
|---|---|---|---|
| RGE rate recovery and rainfed model | `analysis_inputs/scripts/101_rebuild_rge_weather_n_inference.py` | `rge_weather_n_response_summary.csv`; bootstrap, permutation and leave-one-year-out draws | Primary weather-by-nitrogen inference |
| Irrigation contrast | `analysis_inputs/scripts/104_test_rge_irrigation_mediation.py` | `rge_irrigation_weather_n_mechanism_paired_years_summary.csv`; bootstrap and permutation draws | Concurrent-year irrigation slope contrast |
| MCSE plot-yield panel | `analysis_inputs/scripts/102_build_mcse_plot_remote_sensing_yield_panel.py` | `data/03_gold/mcse_plot_remote_sensing_yield_panel_gold.csv` | Harvest-truncated, plot-linked covariate construction |
| Temporal satellite evaluation | `analysis_inputs/scripts/103_evaluate_mcse_plot_rs_yield_temporal.py` | `outputs/tables/mcse_plot_remote_sensing_temporal_evaluation.csv`; predictions and diagnostic records | Nested leave-one-year-out comparison |
| Robustness and outer-year diagnostics | `analysis_inputs/scripts/107_submission_robustness_and_remote_diagnostics.py` | Crop-year support, leave-two-year-out estimates and remote outer-year predictions, metrics and selected penalties | Finite-year and temporal-validation diagnostics |
| Main and Extended Data figures | `analysis_inputs/scripts/105_build_v7_integrity_figure_suite.py`; `analysis_inputs/scripts/106_build_v7_extended_data_figures.py` | `analysis_outputs/figure_source_data_v7/` | Figure generation and panel-level source data |

## Supplementary Figure Legends

**Figure S1 | Fertilizer-rate schedule audit.** Comparison of every reported public rate with the crop-specific F1–F9 schedule and identification of later blank fields recovered from that schedule. The audit compares provider values before any blank-rate recovery.

**Figure S2 | Full weather-model sensitivity.** Heat-dry, heat-only and dry-day-only nitrogen interaction estimates for rainfed and all-plot specifications, shown with and without the nitrogen-by-time adjustment. Horizontal bars are year-clustered 95% confidence intervals.

**Figure S3 | Annual-unit robustness.** Complete leave-one-year-out coefficient distribution, complete-year bootstrap distribution and year-label permutation distribution for the rainfed heat-dry interaction. Each resampling unit is one harvest year.

**Figure S4 | Irrigation-contrast robustness.** Alternative weather definitions and the full bootstrap and permutation output for the concurrent-year irrigation-by-weather interaction. The concurrent panel includes only 2003–2025 years with both irrigation states.

**Figure S5 | Measured soil inorganic nitrogen calibration.** Nitrate, ammonium, gravimetric moisture and soil temperature from the public 2002 RGE sampling campaign plotted against documented treatment rate. This figure characterizes a single-season gradient measurement.

**Figure S6 | Remote-sensing data integrity.** Plot masks, boundary support, clear fraction, observation count and harvest-cutoff feature support for the KBS Gold cubes.

**Figure S7 | Complete satellite validation.** Outer-fold model metrics, temporally separated RMSE comparisons and year-block MSE-gain diagnostics for the management and satellite feature blocks.

**Figure S8 | Crop-year support and finite-year robustness.** Each rainfed harvest year has one crop group; the dot area in panel a is proportional to records in that crop-year. Panel b shows the distribution from every model excluding two harvest years, and panel c orders those same 351 estimates. Crop-specific nitrogen slopes are included because crop intercepts are collinear with year fixed effects. Panel d summarizes years and maximum plot support by crop.

**Figure S9 | Full outer-year remote-sensing diagnostics.** Every point in panel a is a calendar year held out of all preprocessing, ridge-penalty selection and fitting. Panels b and c show pooled outer-fold predictions for the management-only and management-plus-Landsat models, respectively. Panel d gives the ridge penalty selected inside each training set. The analysis uses 830 Landsat-eligible observations from 37 calendar years.

**Figure S10 | Remote-sensing Gold-cube QA and plot support.** KBS Sentinel-2 false-colour imagery and the pixel-level clear fraction, observation count, QA mode, time-gap support, layer availability and phenology-slot quality checks used to construct harvest-truncated covariates. White outlines identify the KBS plot support used for plot-resolved extraction.

## Data and Code Availability

The public reproducibility archive contains source CSV files for every main and supplementary figure panel, model summaries, bootstrap and permutation draws, plotted values and scripts used to create the processed panels and figures. Provider-controlled raw data are identified by catalog accession and access condition rather than redistributed.
