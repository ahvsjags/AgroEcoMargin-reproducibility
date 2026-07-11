#!/usr/bin/env python3
"""Re-estimate weather-conditioned N response in the KBS Resource Gradient Experiment.

The original paper panel mixed MCSE and RGE rows and used an almost-saturated
binary extreme label. This analysis uses the published RGE fixed N gradient,
continuous pre-specified heat/dry stress, plot and year fixed effects, and
year-block uncertainty diagnostics. It intentionally reports effect
modification within this experiment, not a universal causal fertilizer effect.
"""

from __future__ import annotations

import csv
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf


BASE = Path(os.environ.get(
    "AGROECOMARGIN_ANALYSIS_INPUTS",
    r"D:\AgroEcoMargin_manuscript_work_20260710\analysis_inputs" if os.name == "nt" else "/mnt/AgroEcoMargin/data_acquisition/reanalysis_inputs",
))
RGE_RAW = BASE / "rge" / "077_agronomic_yields_resource_gradient_experiment.csv"
CLIMATE = BASE / "kbs_climate_annual_gold.csv"
OUT = BASE.parent / "analysis_outputs"

SEED = 20260710
BOOTSTRAPS = 240
PERMUTATIONS = 600


def header_row(path: Path, prefix: str) -> int:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return next(i for i, line in enumerate(lines) if line.startswith(prefix))


def read_rge() -> pd.DataFrame:
    raw = pd.read_csv(RGE_RAW, skiprows=header_row(RGE_RAW, "date,plot,"))
    raw = raw[pd.to_numeric(raw["year"], errors="coerce").notna()].copy()
    raw["year"] = raw["year"].astype(int)
    for col in ["plot", "fertilizer_rate_kg_ha", "yield_kg_ha"]:
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    raw["irrigated_binary"] = (raw["irrigated"].astype(str).str.lower() == "t").astype(int)
    raw["crop_group"] = raw["crop"].map(
        lambda x: "corn" if "Zea" in str(x) else ("soybean" if "Glycine" in str(x) else ("wheat" if "Triticum" in str(x) else str(x)))
    )
    # The current provider file retains F1--F9 treatment identifiers through
    # 2025 but has blank rate cells after 2019. KBS documents the crop-specific
    # rate schedule: corn 0--291, wheat 0--179, and unfertilized soybean except
    # in 2012. Recover only these blanks and fail if recorded rates disagree.
    rate_schedule = {
        "corn": [0, 34, 67, 101, 134, 168, 202, 246, 291],
        "wheat": [0, 22, 45, 67, 90, 112, 134, 157, 179],
        "soybean": [0, 0, 0, 0, 0, 0, 0, 0, 0],
    }
    soybean_2012 = [0, 17, 34, 50, 67, 84, 101, 123, 146]

    def scheduled_rate(row: pd.Series) -> float:
        treatment_index = int(row["treatment"]) - 1
        if row["crop_group"] == "soybean" and int(row["year"]) == 2012:
            return float(soybean_2012[treatment_index])
        return float(rate_schedule[str(row["crop_group"])][treatment_index])

    raw["scheduled_fertilizer_rate_kg_ha"] = raw.apply(scheduled_rate, axis=1)
    recorded = raw["fertilizer_rate_kg_ha"].notna()
    if not np.allclose(
        raw.loc[recorded, "fertilizer_rate_kg_ha"],
        raw.loc[recorded, "scheduled_fertilizer_rate_kg_ha"],
    ):
        raise ValueError("Recorded RGE fertilizer rates disagree with the documented F1--F9 schedule.")
    raw["n_rate_recovered_from_documented_schedule"] = raw["fertilizer_rate_kg_ha"].isna()
    raw["fertilizer_rate_kg_ha"] = raw["fertilizer_rate_kg_ha"].fillna(raw["scheduled_fertilizer_rate_kg_ha"])

    climate = pd.read_csv(CLIMATE)
    keep = ["year", "heat_days_30c_gs", "dry_days_lt1mm_gs", "longest_dry_spell_gs", "precip_gs_mm"]
    data = raw.merge(climate[keep], on="year", how="left")
    data["n100"] = data["fertilizer_rate_kg_ha"] / 100.0
    data["time_c"] = (data["year"] - data["year"].mean()) / 10.0
    for feature in ["heat_days_30c_gs", "dry_days_lt1mm_gs", "longest_dry_spell_gs", "precip_gs_mm"]:
        data[f"{feature}_z"] = (data[feature] - data[feature].mean()) / data[feature].std(ddof=0)
    # Pre-specified equal-weight stress index: high heat days and dry days.
    data["heat_dry_stress_z"] = (data["heat_days_30c_gs_z"] + data["dry_days_lt1mm_gs_z"]) / math.sqrt(2.0)
    required = ["yield_kg_ha", "n100", "plot", "year", "heat_dry_stress_z", "crop_group"]
    return data.dropna(subset=required).copy()


def fit(data: pd.DataFrame, stress: str, include_time_trend: bool = True) -> tuple[object, str]:
    extras = " + n100:time_c" if include_time_trend else ""
    formula = f"yield_kg_ha ~ C(year) + C(plot) + n100:{stress} + C(crop_group):n100{extras}"
    plain = smf.ols(formula, data).fit()
    groups = data.loc[plain.model.data.row_labels, "year"]
    robust = smf.ols(formula, data).fit(cov_type="cluster", cov_kwds={"groups": groups})
    term = f"n100:{stress}"
    return robust, term


def effect_record(data: pd.DataFrame, analysis_id: str, population: str, stress: str, time_adjusted: bool) -> dict[str, object]:
    model, term = fit(data, stress, time_adjusted)
    ci = model.conf_int().loc[term]
    return {
        "analysis_id": analysis_id,
        "population": population,
        "stress_definition": stress,
        "time_trend_adjusted": time_adjusted,
        "n_rows": int(model.nobs),
        "n_years": int(data.loc[model.model.data.row_labels, "year"].nunique()),
        "n_plots": int(data.loc[model.model.data.row_labels, "plot"].nunique()),
        "effect_kg_ha_per_100kgN_per_1sd_stress": float(model.params[term]),
        "cluster_year_se": float(model.bse[term]),
        "cluster_year_p": float(model.pvalues[term]),
        "cluster_year_ci_low": float(ci.iloc[0]),
        "cluster_year_ci_high": float(ci.iloc[1]),
        "r_squared": float(model.rsquared),
    }


def year_bootstrap(data: pd.DataFrame, stress: str, rng: np.random.Generator) -> np.ndarray:
    years = np.array(sorted(data["year"].unique()))
    values: list[float] = []
    for _ in range(BOOTSTRAPS):
        draw = rng.choice(years, size=len(years), replace=True)
        blocks: list[pd.DataFrame] = []
        for index, year in enumerate(draw):
            block = data[data["year"].eq(year)].copy()
            block["year_boot"] = index
            blocks.append(block)
        sample = pd.concat(blocks, ignore_index=True)
        formula = f"yield_kg_ha ~ C(year_boot) + C(plot) + n100:{stress} + C(crop_group):n100 + n100:time_c"
        try:
            model = smf.ols(formula, sample).fit()
            value = float(model.params[f"n100:{stress}"])
            if math.isfinite(value):
                values.append(value)
        except Exception:
            continue
    return np.asarray(values, dtype=float)


def year_permutation(data: pd.DataFrame, stress: str, observed: float, rng: np.random.Generator) -> np.ndarray:
    by_year = data.groupby("year")[stress].first()
    years = by_year.index.to_numpy()
    original = by_year.to_numpy()
    values: list[float] = []
    for _ in range(PERMUTATIONS):
        permuted = dict(zip(years, rng.permutation(original)))
        sample = data.copy()
        sample["permuted_stress"] = sample["year"].map(permuted)
        try:
            model, term = fit(sample, "permuted_stress", include_time_trend=True)
            value = float(model.params[term])
            if math.isfinite(value):
                values.append(value)
        except Exception:
            continue
    return np.asarray(values, dtype=float)


def leave_one_year_out(data: pd.DataFrame, stress: str) -> pd.DataFrame:
    rows = []
    for year in sorted(data["year"].unique()):
        subset = data.loc[~data["year"].eq(year)].copy()
        record = effect_record(subset, f"leave_out_{year}", "rainfed", stress, True)
        record["excluded_year"] = int(year)
        rows.append(record)
    return pd.DataFrame(rows)


def stress_strata(data: pd.DataFrame) -> pd.DataFrame:
    rainfed = data[data["irrigated_binary"].eq(0)].copy()
    annual = rainfed.groupby("year")["heat_dry_stress_z"].first()
    q1, q2 = annual.quantile([1 / 3, 2 / 3]).tolist()
    rainfed["stress_tercile"] = pd.cut(
        rainfed["heat_dry_stress_z"], [-np.inf, q1, q2, np.inf], labels=["low", "middle", "high"], include_lowest=True
    )
    return (
        rainfed.groupby(["stress_tercile", "fertilizer_rate_kg_ha"], observed=True)
        .agg(yield_mean_kg_ha=("yield_kg_ha", "mean"), yield_sd_kg_ha=("yield_kg_ha", "std"), n=("yield_kg_ha", "size"))
        .reset_index()
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = read_rge()
    populations = {"rainfed": data[data["irrigated_binary"].eq(0)].copy(), "all_plots": data.copy()}
    rows: list[dict[str, object]] = []
    for population, subset in populations.items():
        for stress in ["heat_dry_stress_z", "heat_days_30c_gs_z", "dry_days_lt1mm_gs_z"]:
            for adjusted in [False, True]:
                rows.append(effect_record(subset, f"{population}_{stress}_{'trend' if adjusted else 'base'}", population, stress, adjusted))
    summary = pd.DataFrame(rows)
    primary = populations["rainfed"]
    primary_row = summary.query("analysis_id == 'rainfed_heat_dry_stress_z_trend'").iloc[0]
    rng = np.random.default_rng(SEED)
    bootstrap = year_bootstrap(primary, "heat_dry_stress_z", rng)
    permutation = year_permutation(primary, "heat_dry_stress_z", float(primary_row.effect_kg_ha_per_100kgN_per_1sd_stress), rng)
    if len(bootstrap):
        summary.loc[summary.analysis_id.eq("rainfed_heat_dry_stress_z_trend"), "year_block_bootstrap_ci_low"] = np.quantile(bootstrap, 0.025)
        summary.loc[summary.analysis_id.eq("rainfed_heat_dry_stress_z_trend"), "year_block_bootstrap_ci_high"] = np.quantile(bootstrap, 0.975)
    if len(permutation):
        observed = abs(float(primary_row.effect_kg_ha_per_100kgN_per_1sd_stress))
        p_perm = (1 + int(np.sum(np.abs(permutation) >= observed))) / (1 + len(permutation))
        summary.loc[summary.analysis_id.eq("rainfed_heat_dry_stress_z_trend"), "year_label_permutation_p_two_sided"] = p_perm
    summary.to_csv(OUT / "rge_weather_n_response_summary.csv", index=False)
    pd.DataFrame({"bootstrap_effect": bootstrap}).to_csv(OUT / "rge_weather_n_response_year_block_bootstrap.csv", index=False)
    pd.DataFrame({"permuted_effect": permutation}).to_csv(OUT / "rge_weather_n_response_year_label_permutation.csv", index=False)
    leave_one_year_out(primary, "heat_dry_stress_z").to_csv(OUT / "rge_weather_n_response_leave_one_year_out.csv", index=False)
    stress_strata(data).to_csv(OUT / "rge_weather_n_response_stress_strata.csv", index=False)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
