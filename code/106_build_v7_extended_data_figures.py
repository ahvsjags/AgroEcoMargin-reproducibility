#!/usr/bin/env python3
"""Build Extended Data figures for the integrity-rebuilt manuscript."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("v7fig", HERE / "105_build_v7_integrity_figure_suite.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot import figure helpers.")
V7 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(V7)

OUT = V7.RESULTS / "extended_data_v7_integrity_rebuild"
SOURCE = V7.SOURCE


def label(ax: plt.Axes, value: str) -> None:
    ax.text(-0.12, 1.20, value, transform=ax.transAxes, fontsize=10, fontweight="bold", va="top")


def save(fig: plt.Figure, stem: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for suffix, kwargs in {"pdf": {}, "svg": {}, "png": {"dpi": 600}, "tiff": {"dpi": 600}}.items():
        fig.savefig(OUT / f"{stem}.{suffix}", bbox_inches="tight", facecolor="white", **kwargs)
    plt.close(fig)


def source(name: str, table: pd.DataFrame) -> None:
    SOURCE.mkdir(parents=True, exist_ok=True)
    table.to_csv(SOURCE / name, index=False)


def ed1_schedule(data: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(7.25, 2.5), layout="constrained")
    observed = data.loc[data.fertilizer_rate_kg_ha.notna()].copy()
    axes[0].scatter(observed.scheduled_n_rate_kg_ha, observed.fertilizer_rate_kg_ha, s=9, alpha=0.55, color=V7.COLORS["irrigated"], edgecolor="none")
    maximum = max(observed.scheduled_n_rate_kg_ha.max(), observed.fertilizer_rate_kg_ha.max())
    axes[0].plot([0, maximum], [0, maximum], color=V7.COLORS["ink"], lw=1, ls="--")
    axes[0].set(xlabel="Documented schedule (kg N ha$^{-1}$)", ylabel="Reported rate (kg N ha$^{-1}$)", title="Exact agreement for every reported rate")
    axes[0].set_aspect("equal", adjustable="box"); label(axes[0], "a")
    recovery = data.groupby(["year", "crop_group"], as_index=False).agg(records=("yield_kg_ha", "size"), recovered=("rate_recovered", "sum"))
    for crop, part in recovery.groupby("crop_group"):
        axes[1].plot(part.year, part.recovered, marker="o", ms=2.5, lw=1.2, label=crop.title())
    axes[1].set(xlabel="Harvest year", ylabel="Recovered rate records", title="Recovery begins when provider rate cells become blank")
    axes[1].legend(fontsize=6.2, ncol=1); label(axes[1], "b")
    check = observed.groupby("crop_group", as_index=False).agg(reported=("fertilizer_rate_kg_ha", "size"))
    recovered = data.loc[data.rate_recovered].groupby("crop_group", as_index=False).agg(recovered=("n_rate_kg_ha", "size"))
    check = check.merge(recovered, on="crop_group", how="outer").fillna(0)
    x = np.arange(len(check)); axes[2].bar(x - 0.18, check.reported, 0.35, label="Reported", color=V7.COLORS["slate"]); axes[2].bar(x + 0.18, check.recovered, 0.35, label="Recovered", color=V7.COLORS["gold"])
    axes[2].set_xticks(x, check.crop_group.str.title()); axes[2].set_ylabel("Yield records"); axes[2].set_title("Audit counts by crop"); axes[2].legend(fontsize=6.2); label(axes[2], "c")
    source("ed_fig1_schedule_audit.csv", pd.concat([observed.assign(status="reported"), data.loc[data.rate_recovered].assign(status="recovered")], ignore_index=True))
    save(fig, "ExtendedData_Fig1_schedule_recovery_audit")


def ed2_sensitivity() -> None:
    table = pd.read_csv(V7.SUMMARY)
    fig, ax = plt.subplots(figsize=(7.25, 3.55), layout="constrained")
    stress_labels = {
        "heat_dry_stress_z": "Heat-dry index",
        "heat_days_30c_gs_z": "Heat days >30 C",
        "dry_days_lt1mm_gs_z": "Dry days <1 mm",
    }
    table = table.assign(
        label=(
            table.population.replace({"rainfed": "Rainfed", "all_plots": "All plots"})
            + " | "
            + table.stress_definition.map(stress_labels).fillna(table.stress_definition)
            + " | "
            + np.where(table.time_trend_adjusted, "N x time", "base")
        )
    )
    y = np.arange(len(table))[::-1]
    ax.axvline(0, color="#9BA8AE", lw=0.8, ls="--")
    colors = [V7.COLORS["rainfed"] if value == "rainfed" else V7.COLORS["irrigated"] for value in table.population]
    for yy, row, color in zip(y, table.itertuples(), colors):
        ax.errorbar(row.effect_kg_ha_per_100kgN_per_1sd_stress, yy, xerr=[[row.effect_kg_ha_per_100kgN_per_1sd_stress-row.cluster_year_ci_low], [row.cluster_year_ci_high-row.effect_kg_ha_per_100kgN_per_1sd_stress]], fmt="o", color=color, ecolor=color, capsize=2.2)
    ax.set_yticks(y, table.label); ax.set_xlabel("Change in marginal N response (kg ha$^{-1}$ per 100 kg N / SD)"); ax.set_title("All fixed-effect sensitivity estimates with clustered intervals", loc="left", fontweight="bold")
    source("ed_fig2_full_weather_sensitivity.csv", table)
    save(fig, "ExtendedData_Fig2_weather_model_sensitivity")


def ed3_annual_robustness() -> None:
    loo = pd.read_csv(V7.LOO); boot = pd.read_csv(V7.RESULTS / "rge_weather_n_response_year_block_bootstrap.csv"); perm = pd.read_csv(V7.PERM)
    fig, axes = plt.subplots(1, 3, figsize=(7.25, 2.5), layout="constrained")
    axes[0].axvline(0, color="#9BA8AE", lw=0.8, ls="--"); axes[0].plot(loo.effect_kg_ha_per_100kgN_per_1sd_stress, loo.excluded_year, "o", ms=3, color=V7.COLORS["rainfed"]); axes[0].set(xlabel="Leave-one-year-out interaction", ylabel="Excluded year", title="All leave-one-year-out refits"); label(axes[0], "a")
    axes[1].hist(boot.bootstrap_effect, bins=26, color="#BBD5DA", edgecolor="white"); axes[1].axvline(0, color="#9BA8AE", lw=0.8, ls="--"); axes[1].set(xlabel="Year-block bootstrap interaction", ylabel="Frequency", title="Annual bootstrap"); label(axes[1], "b")
    axes[2].hist(perm.permuted_effect, bins=26, color="#D5DDE0", edgecolor="white"); axes[2].axvline(-254.602, color=V7.COLORS["rainfed"], lw=1.8); axes[2].set(xlabel="Year-label permutation interaction", ylabel="Frequency", title="Annual permutation null"); label(axes[2], "c")
    source("ed_fig3_annual_robustness_loo.csv", loo); source("ed_fig3_annual_robustness_bootstrap.csv", boot); source("ed_fig3_annual_robustness_permutation.csv", perm)
    save(fig, "ExtendedData_Fig3_annual_unit_robustness")


def mechanism_sensitivity(data: pd.DataFrame) -> pd.DataFrame:
    support = data.groupby(["year", "irrigated_binary"]).size().unstack(fill_value=0)
    shared_years = support.index[(support.get(0, 0) > 0) & (support.get(1, 0) > 0)]
    data = data.loc[data.year.isin(shared_years)].copy()
    rows = []
    for field, label_text in [("heat_dry_stress_z", "Heat-dry"), ("heat_days_30c_gs_z", "Heat days"), ("dry_days_lt1mm_gs_z", "Dry days")]:
        formula = f"yield_kg_ha ~ C(year) + C(plot) + C(crop_group):n100 + n100:{field} + n100:irrigated_binary + n100:{field}:irrigated_binary + n100:time_c"
        plain = smf.ols(formula, data).fit(); groups = data.loc[plain.model.data.row_labels, "year"]
        model = smf.ols(formula, data).fit(cov_type="cluster", cov_kwds={"groups": groups})
        term = f"n100:{field}:irrigated_binary"; ci = model.conf_int().loc[term]
        rows.append({"stress_definition": label_text, "estimate": model.params[term], "low": ci.iloc[0], "high": ci.iloc[1], "p_cluster": model.pvalues[term]})
    return pd.DataFrame(rows)


def ed4_mechanism(data: pd.DataFrame) -> None:
    effects = mechanism_sensitivity(data); boot = pd.read_csv(V7.IRR_BOOT); perm = pd.read_csv(V7.IRR_PERM)
    fig, axes = plt.subplots(1, 3, figsize=(7.25, 2.5), layout="constrained")
    yy = np.arange(len(effects))[::-1]; axes[0].axvline(0, color="#9BA8AE", lw=0.8, ls="--")
    axes[0].errorbar(effects.estimate, yy, xerr=[effects.estimate-effects.low, effects.high-effects.estimate], fmt="o", color=V7.COLORS["irrigated"], capsize=2.3)
    axes[0].set_yticks(yy, effects.stress_definition); axes[0].set(xlabel="Irrigation buffering interaction", title="Alternative weather definitions, paired years"); label(axes[0], "a")
    axes[1].hist(boot.bootstrap_buffering_interaction, bins=26, color="#BBD5DA", edgecolor="white"); axes[1].axvline(0, color="#9BA8AE", lw=0.8, ls="--"); axes[1].set(xlabel="Year-block buffering interaction", ylabel="Frequency", title="Bootstrap"); label(axes[1], "b")
    axes[2].hist(perm.permuted_buffering_interaction, bins=26, color="#D5DDE0", edgecolor="white"); axes[2].axvline(437.486, color=V7.COLORS["irrigated"], lw=1.8); axes[2].set(xlabel="Permuted buffering interaction", ylabel="Frequency", title="Year-label null"); label(axes[2], "c")
    source("ed_fig4_irrigation_mechanism_sensitivity.csv", effects); source("ed_fig4_irrigation_bootstrap.csv", boot); source("ed_fig4_irrigation_permutation.csv", perm)
    save(fig, "ExtendedData_Fig4_irrigation_mechanism_robustness")


def ed5_soil(data: pd.DataFrame) -> None:
    soil_path = V7.INPUT / "rge/148_soil_inorganic_nitrogen_moisture_temperature.csv"
    soil = pd.read_csv(soil_path, comment="#"); soil["plot"] = pd.to_numeric(soil["plot"], errors="coerce")
    rates = data.loc[data.year.eq(2002), ["plot", "n_rate_kg_ha", "irrigated_binary", "yield_kg_ha"]].copy()
    rates["plot"] = pd.to_numeric(rates["plot"], errors="coerce")
    rates = rates.drop_duplicates("plot")
    soil = soil.merge(rates, on="plot", how="inner"); soil["mineral_n_ug_g"] = soil.no3 + soil.nh4
    plot = soil.groupby(["plot", "n_rate_kg_ha", "irrigated_binary"], as_index=False).agg(mineral_n_ug_g=("mineral_n_ug_g", "mean"), moisture=("moisture", "mean"), temperature=("temperature", "mean"))
    fig, axes = plt.subplots(1, 3, figsize=(7.25, 2.5), layout="constrained")
    colors = np.where(plot.irrigated_binary.eq(1), V7.COLORS["irrigated"], V7.COLORS["rainfed"])
    axes[0].scatter(plot.n_rate_kg_ha, plot.mineral_n_ug_g, c=colors, s=28, alpha=0.9); axes[0].set(xlabel="N rate (kg ha$^{-1}$)", ylabel="NO$_3$ + NH$_4$ (ug g$^{-1}$)", title="Measured mineral N, 2002"); label(axes[0], "a")
    axes[1].scatter(plot.n_rate_kg_ha, plot.moisture, c=colors, s=28, alpha=0.9); axes[1].set(xlabel="N rate (kg ha$^{-1}$)", ylabel="Gravimetric moisture (%)", title="Sampling context"); label(axes[1], "b")
    axes[2].scatter(plot.mineral_n_ug_g, plot.temperature, c=colors, s=28, alpha=0.9); axes[2].set(xlabel="NO$_3$ + NH$_4$ (ug g$^{-1}$)", ylabel="Soil temperature (C)", title="One-season calibration only"); label(axes[2], "c")
    source("ed_fig5_2002_measured_soil_inorganic_n.csv", plot)
    save(fig, "ExtendedData_Fig5_measured_soil_nitrogen_calibration")


def ed6_remote_integrity() -> None:
    map_data = pd.read_csv(V7.SOURCE / "fig4_plot_level_remote_sensing_map.csv")
    coverage = pd.read_csv(V7.SOURCE / "fig4_remote_sensing_coverage.csv")
    raw = pd.read_csv(V7.MCSE_RS); dual = raw.loc[raw.sentinel2_ndvi_mean.notna()].copy()
    fig, axes = plt.subplots(1, 3, figsize=(7.25, 2.5), layout="constrained")
    plot_a = axes[0].scatter(dual.sentinel2_ndvi_mean, dual.sentinel2_time_gap_days_mean, c=dual.sentinel2_valid_fraction_mean, cmap="YlGn", s=16, alpha=0.8); axes[0].set(xlabel="Preharvest Sentinel-2 NDVI", ylabel="Mean time gap (days)", title="Spectral signal with temporal support"); fig.colorbar(plot_a, ax=axes[0], fraction=0.05, pad=0.02, label="Valid fraction"); label(axes[0], "a")
    plot_b = axes[1].scatter(raw.landsat_available_steps, raw.landsat_time_gap_days_mean, c=raw.landsat_valid_fraction_mean, cmap="viridis", s=11, alpha=0.72); axes[1].set(xlabel="Landsat preharvest available steps", ylabel="Mean time gap (days)", title="Landsat phenology support"); fig.colorbar(plot_b, ax=axes[1], fraction=0.05, pad=0.02, label="Valid fraction"); label(axes[1], "b")
    axes[2].plot(coverage.year, coverage.landsat_records, color=V7.COLORS["slate"], label="Landsat"); axes[2].plot(coverage.year, coverage.sentinel2_records, color=V7.COLORS["irrigated"], label="Sentinel-2"); axes[2].set(xlabel="Harvest year", ylabel="Records", title="Harvest-cutoff coverage"); axes[2].legend(fontsize=6.2); label(axes[2], "c")
    source("ed_fig6_remote_sensing_dual_panel.csv", dual)
    save(fig, "ExtendedData_Fig6_remote_sensing_integrity")


def ed7_remote_validation() -> None:
    metrics = pd.read_csv(V7.SOURCE / "fig4_strict_temporal_validation.csv"); gains = pd.read_csv(V7.SOURCE / "fig4_landsat_mse_gain_bootstrap.csv")
    fig, axes = plt.subplots(1, 2, figsize=(7.25, 2.5), layout="constrained")
    x = np.arange(len(metrics)); colors = [V7.COLORS["slate"], V7.COLORS["rainfed"], V7.COLORS["slate"], V7.COLORS["rainfed"], V7.COLORS["irrigated"], V7.COLORS["stress"]]
    axes[0].bar(x, metrics.rmse_kg_ha, color=colors); axes[0].set_xticks(x, metrics.model, rotation=28, ha="right"); axes[0].set(ylabel="Leave-one-year-out RMSE (kg ha$^{-1}$)", title="All strict temporal model comparisons")
    axes[1].hist(gains.mse_gain, bins=30, color="#D5DDE0", edgecolor="white"); axes[1].axvline(0, color="#9BA8AE", lw=0.8, ls="--"); axes[1].set(xlabel="MSE gain of Landsat vs management", ylabel="Year-block bootstrap frequency", title="No reliable Landsat increment")
    source("ed_fig7_remote_validation_metrics.csv", metrics); source("ed_fig7_remote_validation_bootstrap.csv", gains)
    save(fig, "ExtendedData_Fig7_complete_remote_sensing_validation")


def main() -> None:
    data = V7.load_rge()
    ed1_schedule(data); ed2_sensitivity(); ed3_annual_robustness(); ed4_mechanism(data); ed5_soil(data); ed6_remote_integrity(); ed7_remote_validation()
    print(f"Wrote Extended Data figures to {OUT}")


if __name__ == "__main__":
    main()
