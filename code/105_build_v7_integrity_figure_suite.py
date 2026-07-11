#!/usr/bin/env python3
"""Render the integrity-rebuilt main-figure suite from audited raw outputs."""

from __future__ import annotations

import csv
import math
import os
import re
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.patches import Polygon, Rectangle
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


HERE = Path(__file__).resolve().parent
WORK = Path(os.environ.get("AGROECOMARGIN_MANUSCRIPT_WORK", HERE.parents[1]))
INPUT = Path(os.environ.get("AGROECOMARGIN_ANALYSIS_INPUTS", WORK / "analysis_inputs"))
RESULTS = Path(os.environ.get("AGROECOMARGIN_ANALYSIS_OUTPUTS", WORK / "analysis_outputs"))
FIGURES = RESULTS / "figures_v7_integrity_rebuild"
SOURCE = RESULTS / "figure_source_data_v7"

RGE = INPUT / "rge/077_agronomic_yields_resource_gradient_experiment.csv"
CLIMATE = INPUT / "kbs_climate_annual_gold.csv"
SUMMARY = RESULTS / "rge_weather_n_response_summary.csv"
LOO = RESULTS / "rge_weather_n_response_leave_one_year_out.csv"
PERM = RESULTS / "rge_weather_n_response_year_label_permutation.csv"
IRR_SUMMARY = RESULTS / "rge_irrigation_weather_n_mechanism_paired_years_summary.csv"
IRR_BOOT = RESULTS / "rge_irrigation_weather_n_mechanism_paired_years_bootstrap.csv"
IRR_PERM = RESULTS / "rge_irrigation_weather_n_mechanism_paired_years_permutation.csv"
MCSE_RS = INPUT / "remote_sensing_rebuilt/mcse_plot_remote_sensing_yield_panel_gold.csv"
PLOT_GEOM = INPUT / "remote_sensing_metadata/kbs_plot_id_crosswalk.csv"

COLORS = {
    "ink": "#1F2933",
    "slate": "#708090",
    "rainfed": "#B44A3A",
    "irrigated": "#217A8A",
    "stress": "#933C60",
    "low": "#5A9E6F",
    "mid": "#D5A84B",
    "high": "#B44A3A",
    "gold": "#E5B35A",
    "fog": "#E8ECEF",
}

mpl.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 7.3,
    "axes.linewidth": 0.7,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
})


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, comment="#")


def crop_group(value: str) -> str:
    value = str(value)
    if "Zea" in value:
        return "corn"
    if "Glycine" in value:
        return "soybean"
    if "Triticum" in value:
        return "wheat"
    return "other"


def load_rge() -> pd.DataFrame:
    data = read_csv(RGE)
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data["yield_kg_ha"] = pd.to_numeric(data["yield_kg_ha"], errors="coerce")
    data["fertilizer_rate_kg_ha"] = pd.to_numeric(data["fertilizer_rate_kg_ha"], errors="coerce")
    data["crop_group"] = data["crop"].map(crop_group)
    schedules = {
        "corn": [0, 34, 67, 101, 134, 168, 202, 246, 291],
        "wheat": [0, 22, 45, 67, 90, 112, 134, 157, 179],
        "soybean": [0] * 9,
    }
    soybean_2012 = [0, 17, 34, 50, 67, 84, 101, 123, 146]

    def schedule(row: pd.Series) -> float:
        index = int(row["treatment"]) - 1
        if row["crop_group"] == "soybean" and int(row["year"]) == 2012:
            return soybean_2012[index]
        return schedules[row["crop_group"]][index]

    data["scheduled_n_rate_kg_ha"] = data.apply(schedule, axis=1)
    data["rate_recovered"] = data["fertilizer_rate_kg_ha"].isna()
    observed = data["fertilizer_rate_kg_ha"].notna()
    if not np.allclose(data.loc[observed, "fertilizer_rate_kg_ha"], data.loc[observed, "scheduled_n_rate_kg_ha"]):
        raise ValueError("RGE reported rates do not agree with documented schedule.")
    data["n_rate_kg_ha"] = data["fertilizer_rate_kg_ha"].fillna(data["scheduled_n_rate_kg_ha"])
    climate = pd.read_csv(CLIMATE)
    data = data.merge(climate[["year", "heat_days_30c_gs", "dry_days_lt1mm_gs"]], on="year", how="left")
    data = data.dropna(subset=["yield_kg_ha", "year", "n_rate_kg_ha"]).copy()
    data["year"] = data["year"].astype(int)
    data["n100"] = data["n_rate_kg_ha"] / 100.0
    data["irrigated_binary"] = data["irrigated"].astype(str).str.lower().eq("t").astype(int)
    data["time_c"] = (data["year"] - data["year"].mean()) / 10.0
    for field in ["heat_days_30c_gs", "dry_days_lt1mm_gs"]:
        data[f"{field}_z"] = (data[field] - data[field].mean()) / data[field].std(ddof=0)
    data["heat_dry_stress_z"] = (data["heat_days_30c_gs_z"] + data["dry_days_lt1mm_gs_z"]) / math.sqrt(2.0)
    return data


def panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(-0.12, 1.08, label, transform=ax.transAxes, fontsize=10, fontweight="bold", va="top")


def save(fig: plt.Figure, stem: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    for suffix, kwargs in {
        "pdf": {}, "svg": {}, "png": {"dpi": 600}, "tiff": {"dpi": 600},
    }.items():
        fig.savefig(FIGURES / f"{stem}.{suffix}", bbox_inches="tight", facecolor="white", **kwargs)
    plt.close(fig)


def write_source(name: str, frame: pd.DataFrame) -> None:
    SOURCE.mkdir(parents=True, exist_ok=True)
    frame.to_csv(SOURCE / name, index=False)


def draw_fig1(data: pd.DataFrame) -> None:
    fig = plt.figure(figsize=(7.25, 5.35), layout="constrained")
    gs = fig.add_gridspec(2, 2, width_ratios=[1.35, 1.0], height_ratios=[1.05, 0.95])
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[1, 0])
    ax_d = fig.add_subplot(gs[1, 1])

    schedule_rows = []
    crop_order = ["corn", "wheat", "soybean"]
    for x, crop in enumerate(crop_order):
        rates = data.loc[data.crop_group.eq(crop), ["treatment", "scheduled_n_rate_kg_ha"]].drop_duplicates().sort_values("treatment")
        ax_a.plot(np.repeat(x, len(rates)), rates.scheduled_n_rate_kg_ha, "o", ms=5.4, color=[COLORS["rainfed"], COLORS["gold"], COLORS["low"]][x], mec="white", mew=0.6)
        for _, row in rates.iterrows():
            schedule_rows.append({"crop": crop, "treatment": int(row.treatment), "rate_kg_n_ha": row.scheduled_n_rate_kg_ha})
    ax_a.set_xticks(range(3), ["Corn", "Wheat", "Soybean"])
    ax_a.set_ylabel("Documented N rate (kg ha$^{-1}$)")
    ax_a.set_ylim(-15, 320)
    ax_a.set_title("F1--F9 schedules are crop specific", loc="left", fontsize=8.4, fontweight="bold")
    ax_a.grid(axis="y", color="#DCE2E5", lw=0.5)
    panel_label(ax_a, "a")

    annual = data.groupby("year", as_index=False).agg(rows=("yield_kg_ha", "size"), stress=("heat_dry_stress_z", "first"))
    ax_b.bar(annual.year, annual.rows, color="#CBD5DC", width=0.8)
    ax_b.set_ylabel("Yield records")
    ax_b.set_xlabel("Harvest year")
    sec = ax_b.twinx()
    sec.plot(annual.year, annual.stress, color=COLORS["stress"], lw=1.6, marker="o", ms=2.5)
    sec.axhline(0, color="#AAB6BD", lw=0.6, ls="--")
    sec.set_ylabel("Heat-dry index (SD)", color=COLORS["stress"])
    sec.tick_params(axis="y", colors=COLORS["stress"])
    ax_b.set_title("27 annual climate realizations", loc="left", fontsize=8.4, fontweight="bold")
    ax_b.set_xlim(1998.2, 2025.8)
    panel_label(ax_b, "b")

    support = data.groupby(["year", "irrigated_binary"]).size().unstack(fill_value=0)
    shared_years = support.index[(support.get(0, 0) > 0) & (support.get(1, 0) > 0)]
    paired = data.loc[data.year.isin(shared_years)]
    tiles = [
        ("27", "rainfed climate\nyears", COLORS["stress"]),
        (str(len(shared_years)), "concurrent irrigation\nyears", COLORS["irrigated"]),
        (str(paired["plot"].nunique()), "paired experimental\nplots", COLORS["gold"]),
        (f"{len(paired):,}", "paired mechanism\nyield records", COLORS["rainfed"]),
    ]
    ax_c.set_xlim(0, 2); ax_c.set_ylim(0, 2); ax_c.axis("off")
    for index, (value, label, color) in enumerate(tiles):
        x, y = index % 2, 1 - index // 2
        ax_c.add_patch(Rectangle((x + 0.05, y + 0.08), 0.88, 0.78, color=color, alpha=0.12, ec=color, lw=1.0))
        ax_c.text(x + 0.49, y + 0.57, value, ha="center", va="center", fontsize=16, fontweight="bold", color=color)
        ax_c.text(x + 0.49, y + 0.27, label, ha="center", va="center", fontsize=7.0, color=COLORS["ink"])
    ax_c.set_title("Annual replication limits inference", loc="left", fontsize=8.4, fontweight="bold", pad=8)
    panel_label(ax_c, "c")

    recovery = data.loc[data.irrigated_binary.eq(0)].groupby("rate_recovered", as_index=False).size()
    recovery["label"] = recovery.rate_recovered.map({False: "Recorded\nrate", True: "Recovered\nfrom schedule"})
    bars = ax_d.bar(recovery.label, recovery["size"], color=[COLORS["slate"], COLORS["gold"]], width=0.62)
    for bar, value in zip(bars, recovery["size"]):
        ax_d.text(bar.get_x() + bar.get_width() / 2, value + 18, f"{value}", ha="center", fontweight="bold")
    ax_d.set_ylim(0, max(recovery["size"]) * 1.18)
    ax_d.set_ylabel("Rainfed analysis records")
    ax_d.set_title("Schedule recovery is auditable", loc="left", fontsize=8.4, fontweight="bold")
    ax_d.grid(axis="y", color="#DCE2E5", lw=0.5)
    panel_label(ax_d, "d")
    write_source("fig1_experiment_schedule.csv", pd.DataFrame(schedule_rows))
    write_source("fig1_annual_coverage_and_stress.csv", annual)
    write_source("fig1_rate_recovery.csv", recovery)
    save(fig, "Fig1_experiment_gradient_and_evidence_base")


def draw_fig2(data: pd.DataFrame) -> None:
    rain = data.loc[data.irrigated_binary.eq(0)].copy()
    yearly = rain.groupby("year")["heat_dry_stress_z"].first()
    q1, q2 = yearly.quantile([1 / 3, 2 / 3]).tolist()
    rain["stress_group"] = pd.cut(rain.heat_dry_stress_z, [-np.inf, q1, q2, np.inf], labels=["Lower", "Middle", "Higher"])
    response = rain.groupby(["stress_group", "n_rate_kg_ha"], observed=True).agg(yield_mean=("yield_kg_ha", "mean"), yield_se=("yield_kg_ha", lambda x: x.std(ddof=1) / math.sqrt(len(x))), n=("yield_kg_ha", "size")).reset_index()
    summary = pd.read_csv(SUMMARY)
    loo = pd.read_csv(LOO)
    perm = pd.read_csv(PERM)
    fig = plt.figure(figsize=(7.25, 5.35), layout="constrained")
    gs = fig.add_gridspec(2, 2, width_ratios=[1.25, 1.0], height_ratios=[1.05, 0.95])
    ax_a = fig.add_subplot(gs[0, 0]); ax_b = fig.add_subplot(gs[0, 1]); ax_c = fig.add_subplot(gs[1, 0]); ax_d = fig.add_subplot(gs[1, 1])
    palette = {"Lower": COLORS["low"], "Middle": COLORS["mid"], "Higher": COLORS["high"]}
    for group, part in response.groupby("stress_group", observed=True):
        ax_a.errorbar(part.n_rate_kg_ha, part.yield_mean, yerr=part.yield_se, color=palette[str(group)], lw=1.7, marker="o", ms=3.3, capsize=2, label=str(group))
    ax_a.set_xlabel("Nitrogen rate (kg ha$^{-1}$)"); ax_a.set_ylabel("Rainfed yield (kg ha$^{-1}$)")
    ax_a.legend(title="Heat-dry tercile", ncol=1, fontsize=6.5, title_fontsize=6.7, loc="upper left")
    ax_a.set_title("Pooled descriptive means by annual stress", loc="left", fontsize=8.0, fontweight="bold")
    ax_a.grid(color="#E2E7E9", lw=0.45); panel_label(ax_a, "a")

    targets = [
        ("rainfed_heat_dry_stress_z_trend", "Heat-dry index"),
        ("rainfed_heat_days_30c_gs_z_trend", "Heat days"),
        ("rainfed_dry_days_lt1mm_gs_z_trend", "Dry days"),
    ]
    forest = []
    for key, label in targets:
        row = summary.loc[summary.analysis_id.eq(key)].iloc[0]
        forest.append({"specification": label, "estimate": row.effect_kg_ha_per_100kgN_per_1sd_stress, "low": row.cluster_year_ci_low, "high": row.cluster_year_ci_high})
    forest = pd.DataFrame(forest)
    y = np.arange(len(forest))[::-1]
    ax_b.axvline(0, color="#9BA8AE", lw=0.8, ls="--")
    ax_b.errorbar(forest.estimate, y, xerr=[forest.estimate - forest.low, forest.high - forest.estimate], fmt="o", color=COLORS["rainfed"], ecolor=COLORS["rainfed"], capsize=2.5)
    ax_b.set_yticks(y, forest.specification); ax_b.set_xlabel("Change in N response\nkg ha$^{-1}$ per 100 kg N / SD")
    ax_b.set_title("Fixed-effect interaction estimates", loc="left", fontsize=8.4, fontweight="bold")
    panel_label(ax_b, "b")

    ax_c.axvline(0, color="#9BA8AE", lw=0.8, ls="--")
    ax_c.plot(loo.effect_kg_ha_per_100kgN_per_1sd_stress, loo.excluded_year, "o", ms=3.2, color=COLORS["rainfed"], alpha=0.92)
    ax_c.set_xlabel("Heat-dry interaction after excluding year")
    ax_c.set_ylabel("Excluded year")
    ax_c.set_title("No single year reverses the fixed-effect direction", loc="left", fontsize=8.4, fontweight="bold")
    panel_label(ax_c, "c")

    observed = float(summary.loc[summary.analysis_id.eq("rainfed_heat_dry_stress_z_trend"), "effect_kg_ha_per_100kgN_per_1sd_stress"].iloc[0])
    ax_d.hist(perm.permuted_effect, bins=28, color="#C9D1D5", edgecolor="white")
    ax_d.axvline(observed, color=COLORS["rainfed"], lw=2)
    ax_d.axvline(-observed, color=COLORS["rainfed"], lw=1.1, ls="--")
    ax_d.text(0.04, 0.93, "year-label permutation\np = 0.236", transform=ax_d.transAxes, va="top", fontsize=7.1, color=COLORS["ink"])
    ax_d.set_xlabel("Permuted interaction estimate")
    ax_d.set_ylabel("Frequency")
    ax_d.set_title("Annual null distribution", loc="left", fontsize=8.4, fontweight="bold")
    panel_label(ax_d, "d")
    write_source("fig2_rainfed_stress_stratified_response.csv", response)
    write_source("fig2_fixed_effect_estimates.csv", forest)
    write_source("fig2_leave_one_year_out.csv", loo)
    write_source("fig2_year_label_permutation.csv", perm)
    save(fig, "Fig2_weather_conditioned_nitrogen_response")


def draw_fig3(data: pd.DataFrame) -> None:
    support = data.groupby(["year", "irrigated_binary"]).size().unstack(fill_value=0)
    shared_years = support.index[(support.get(0, 0) > 0) & (support.get(1, 0) > 0)]
    data = data.loc[data.year.isin(shared_years)].copy()
    yearly = data.groupby("year")["heat_dry_stress_z"].first()
    q1, q2 = yearly.quantile([1 / 3, 2 / 3]).tolist()
    data = data.copy()
    data["stress_group"] = pd.cut(data.heat_dry_stress_z, [-np.inf, q1, q2, np.inf], labels=["Lower", "Middle", "Higher"])
    empirical = data.loc[data.stress_group.isin(["Lower", "Higher"])].groupby(["irrigated_binary", "stress_group", "n_rate_kg_ha"], observed=True).agg(yield_mean=("yield_kg_ha", "mean"), yield_se=("yield_kg_ha", lambda x: x.std(ddof=1) / math.sqrt(len(x))), n=("yield_kg_ha", "size")).reset_index()
    mechanism = pd.read_csv(IRR_SUMMARY).iloc[0]
    boot = pd.read_csv(IRR_BOOT)
    perm = pd.read_csv(IRR_PERM)
    fig = plt.figure(figsize=(7.25, 5.35), layout="constrained")
    gs = fig.add_gridspec(2, 2, width_ratios=[1.3, 1.0], height_ratios=[1.1, 0.9])
    ax_a = fig.add_subplot(gs[0, 0]); ax_b = fig.add_subplot(gs[0, 1]); ax_c = fig.add_subplot(gs[1, 0]); ax_d = fig.add_subplot(gs[1, 1])
    styles = {(0, "Lower"): (COLORS["rainfed"], "-"), (0, "Higher"): (COLORS["rainfed"], "--"), (1, "Lower"): (COLORS["irrigated"], "-"), (1, "Higher"): (COLORS["irrigated"], "--")}
    for (irrig, stress), part in empirical.groupby(["irrigated_binary", "stress_group"], observed=True):
        color, style = styles[(int(irrig), str(stress))]
        label = f"{'Irrigated' if irrig else 'Rainfed'}, {str(stress).lower()} stress"
        ax_a.plot(part.n_rate_kg_ha, part.yield_mean, color=color, ls=style, lw=1.8, marker="o", ms=3, label=label)
    ax_a.set_xlabel("Nitrogen rate (kg ha$^{-1}$)"); ax_a.set_ylabel("Yield (kg ha$^{-1}$)")
    ax_a.legend(fontsize=6.0, ncol=2, loc="upper left")
    ax_a.grid(color="#E2E7E9", lw=0.45)
    ax_a.set_title("Pooled descriptive gradients by stress", loc="left", fontsize=8.0, fontweight="bold")
    panel_label(ax_a, "a")

    effect = pd.DataFrame({
        "contrast": ["Rainfed N × stress", "Irrigation buffering"],
        "estimate": [mechanism.rainfed_n_by_stress_effect_kg_ha_per_100kgN_per_1sd, mechanism.irrigation_buffering_interaction_kg_ha_per_100kgN_per_1sd],
        "low": [mechanism.rainfed_cluster_ci_low, mechanism.buffer_cluster_ci_low],
        "high": [mechanism.rainfed_cluster_ci_high, mechanism.buffer_cluster_ci_high],
        "color": [COLORS["rainfed"], COLORS["irrigated"]],
    })
    yy = np.arange(2)[::-1]
    ax_b.axvline(0, color="#9BA8AE", lw=0.8, ls="--")
    for y, row in zip(yy, effect.itertuples()):
        ax_b.errorbar(row.estimate, y, xerr=[[row.estimate-row.low], [row.high-row.estimate]], fmt="o", color=row.color, ecolor=row.color, capsize=2.5)
    ax_b.set_yticks(yy, effect.contrast); ax_b.set_xlabel("kg ha$^{-1}$ per 100 kg N / SD")
    ax_b.set_title("Mechanism interaction", loc="left", fontsize=8.4, fontweight="bold")
    panel_label(ax_b, "b")

    ax_c.hist(boot.bootstrap_buffering_interaction, bins=25, color="#B7D8DE", edgecolor="white")
    ax_c.axvline(mechanism.irrigation_buffering_interaction_kg_ha_per_100kgN_per_1sd, color=COLORS["irrigated"], lw=2)
    ax_c.axvline(0, color="#9BA8AE", lw=0.8, ls="--")
    ax_c.text(0.04, 0.93, "year-block bootstrap\n95% interval crosses zero", transform=ax_c.transAxes, va="top", fontsize=7.0)
    ax_c.set_xlabel("Buffering interaction"); ax_c.set_ylabel("Frequency")
    ax_c.set_title("Annual resampling", loc="left", fontsize=8.4, fontweight="bold")
    panel_label(ax_c, "c")

    ax_d.hist(perm.permuted_buffering_interaction, bins=28, color="#D6DDE0", edgecolor="white")
    ax_d.axvline(mechanism.irrigation_buffering_interaction_kg_ha_per_100kgN_per_1sd, color=COLORS["irrigated"], lw=2)
    ax_d.axvline(-mechanism.irrigation_buffering_interaction_kg_ha_per_100kgN_per_1sd, color=COLORS["irrigated"], lw=1.1, ls="--")
    ax_d.text(0.04, 0.93, f"year-label permutation\np = {mechanism.buffer_year_label_permutation_p_two_sided:.3f}", transform=ax_d.transAxes, va="top", fontsize=7.0)
    ax_d.set_xlabel("Permuted buffering interaction"); ax_d.set_ylabel("Frequency")
    ax_d.set_title("Mechanism placebo", loc="left", fontsize=8.4, fontweight="bold")
    panel_label(ax_d, "d")
    write_source("fig3_irrigation_stress_response.csv", empirical)
    write_source("fig3_mechanism_effects.csv", effect.drop(columns="color"))
    write_source("fig3_mechanism_bootstrap.csv", boot)
    write_source("fig3_mechanism_permutation.csv", perm)
    save(fig, "Fig3_irrigation_buffering_mechanism")


def make_pipeline(features: list[str], categorical: list[str]) -> Pipeline:
    numeric = [field for field in features if field not in categorical]
    return Pipeline([
        ("prepare", ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
            ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
        ])),
        ("ridge", Ridge()),
    ])


def choose_alpha(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, features: list[str], categorical: list[str]) -> float:
    candidates = [0.1, 1.0, 10.0, 100.0, 1000.0]
    scores = []
    for alpha in candidates:
        fold_scores = []
        for tr, va in GroupKFold(n_splits=min(5, len(np.unique(groups)))).split(X, y, groups):
            model = make_pipeline(features, categorical).set_params(ridge__alpha=alpha)
            model.fit(X.iloc[tr][features], y[tr])
            fold_scores.append(mean_squared_error(y[va], model.predict(X.iloc[va][features])))
        scores.append(float(np.mean(fold_scores)))
    return candidates[int(np.argmin(scores))]


def year_held_out_rmse(data: pd.DataFrame, features: list[str], categorical: list[str]) -> tuple[float, np.ndarray]:
    X = data[features]; y = data.yield_kg_ha.to_numpy(float); groups = data.year.to_numpy(int); predictions = np.zeros(len(data))
    for tr, te in LeaveOneGroupOut().split(X, y, groups):
        alpha = choose_alpha(X.iloc[tr], y[tr], groups[tr], features, categorical)
        model = make_pipeline(features, categorical).set_params(ridge__alpha=alpha)
        model.fit(X.iloc[tr][features], y[tr]); predictions[te] = model.predict(X.iloc[te][features])
    return float(mean_squared_error(y, predictions) ** 0.5), predictions


def wkt_coords(text: str) -> list[tuple[float, float]]:
    pairs = re.findall(r"(-?\d+\.\d+)\s+(-?\d+\.\d+)", str(text))
    return [(float(x), float(y)) for x, y in pairs]


def draw_fig4() -> None:
    panel = pd.read_csv(MCSE_RS)
    categorical = ["crop_group", "treatment", "replicate"]
    landsat = [
        "landsat_ndvi_mean", "landsat_ndvi_max", "landsat_ndvi_last", "landsat_ndvi_slope", "landsat_ndwi_mean", "landsat_nbr_mean", "landsat_red_mean", "landsat_nir08_mean", "landsat_swir16_mean", "landsat_swir22_mean", "landsat_clear_fraction_mean", "landsat_obs_count_mean", "landsat_valid_fraction_mean", "landsat_time_gap_days_mean",
    ]
    sentinel = [field.replace("landsat", "sentinel2") for field in landsat]
    all_landsat = panel.loc[panel.landsat_ndvi_mean.notna()].copy()
    rmse_m0, pred_m0 = year_held_out_rmse(all_landsat, categorical, categorical)
    rmse_landsat, pred_landsat = year_held_out_rmse(all_landsat, categorical + landsat, categorical)
    dual = panel.loc[panel.year.between(2017, 2023) & panel.sentinel2_ndvi_mean.notna()].copy()
    rmse_m0_dual, _ = year_held_out_rmse(dual, categorical, categorical)
    rmse_landsat_dual, _ = year_held_out_rmse(dual, categorical + landsat, categorical)
    rmse_s2, _ = year_held_out_rmse(dual, categorical + sentinel, categorical)
    rmse_both, _ = year_held_out_rmse(dual, categorical + landsat + sentinel, categorical)
    y = all_landsat.yield_kg_ha.to_numpy(float)
    by_year = {year: np.flatnonzero(all_landsat.year.to_numpy() == year) for year in all_landsat.year.unique()}
    rng = np.random.default_rng(20260710); gains = []
    for _ in range(3000):
        index = np.concatenate([by_year[year] for year in rng.choice(list(by_year), len(by_year), replace=True)])
        gains.append(float(np.mean((y[index] - pred_m0[index]) ** 2) - np.mean((y[index] - pred_landsat[index]) ** 2)))
    metrics = pd.DataFrame([
        {"subset": "1989--2025 Landsat", "model": "Management only", "rmse_kg_ha": rmse_m0},
        {"subset": "1989--2025 Landsat", "model": "+ plot Landsat", "rmse_kg_ha": rmse_landsat},
        {"subset": "2017--2023 dual-sensor", "model": "Management only", "rmse_kg_ha": rmse_m0_dual},
        {"subset": "2017--2023 dual-sensor", "model": "+ Landsat", "rmse_kg_ha": rmse_landsat_dual},
        {"subset": "2017--2023 dual-sensor", "model": "+ Sentinel-2", "rmse_kg_ha": rmse_s2},
        {"subset": "2017--2023 dual-sensor", "model": "+ both sensors", "rmse_kg_ha": rmse_both},
    ])
    coverage = panel.assign(landsat=panel.landsat_ndvi_mean.notna(), sentinel2=panel.sentinel2_ndvi_mean.notna()).groupby("year", as_index=False).agg(landsat_records=("landsat", "sum"), sentinel2_records=("sentinel2", "sum"))
    map_data = panel.loc[panel.year.eq(2023) & panel.sentinel2_ndvi_mean.notna(), ["plot_numeric_id", "sentinel2_ndvi_mean", "sentinel2_clear_fraction_mean", "treatment", "replicate"]].drop_duplicates("plot_numeric_id")
    geometry = pd.read_csv(PLOT_GEOM)
    mapped = geometry.merge(map_data, on="plot_numeric_id", how="inner")
    fig = plt.figure(figsize=(7.25, 5.35), layout="constrained")
    gs = fig.add_gridspec(2, 2, width_ratios=[1.15, 1.1], height_ratios=[1.05, 0.95])
    ax_a = fig.add_subplot(gs[0, 0]); ax_b = fig.add_subplot(gs[0, 1]); ax_c = fig.add_subplot(gs[1, 0]); ax_d = fig.add_subplot(gs[1, 1])
    norm = Normalize(vmin=mapped.sentinel2_ndvi_mean.quantile(0.02), vmax=mapped.sentinel2_ndvi_mean.quantile(0.98)); cmap = mpl.colormaps["YlGn"]
    for row in mapped.itertuples():
        coords = wkt_coords(row.geometry_wgs84)
        ax_a.add_patch(Polygon(coords, closed=True, facecolor=cmap(norm(row.sentinel2_ndvi_mean)), edgecolor="white", lw=0.5))
    ax_a.set_aspect("equal"); ax_a.autoscale(); ax_a.set_xticks([]); ax_a.set_yticks([])
    colorbar = fig.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax_a, fraction=0.045, pad=0.02)
    colorbar.set_label("Preharvest Sentinel-2 NDVI", fontsize=6.6); colorbar.ax.tick_params(labelsize=6)
    ax_a.set_title("Plot-resolved Sentinel-2 support", loc="left", fontsize=8.0, fontweight="bold")
    panel_label(ax_a, "a")

    ax_b.bar(coverage.year, coverage.landsat_records, color="#8799A4", width=0.85, label="Landsat")
    ax_b.bar(coverage.year, coverage.sentinel2_records, bottom=coverage.landsat_records, color=COLORS["irrigated"], width=0.85, label="Sentinel-2")
    ax_b.set_xlim(1988.2, 2025.8); ax_b.set_ylabel("Plot-yield records with\npreharvest features"); ax_b.set_xlabel("Harvest year")
    ax_b.legend(fontsize=6.4, loc="upper left"); ax_b.set_title("Harvest-cutoff feature availability", loc="left", fontsize=8.4, fontweight="bold")
    ax_b.grid(axis="y", color="#E2E7E9", lw=0.45); panel_label(ax_b, "b")

    labels = ["M0", "+ L", "M0", "+ L", "+ S2", "+ both"]
    values = [rmse_m0, rmse_landsat, rmse_m0_dual, rmse_landsat_dual, rmse_s2, rmse_both]
    positions = np.array([0.0, 0.78, 2.25, 3.03, 3.81, 4.59])
    colors = [COLORS["slate"], COLORS["rainfed"], COLORS["slate"], COLORS["rainfed"], COLORS["irrigated"], COLORS["stress"]]
    bars = ax_c.bar(positions, values, color=colors, width=0.60)
    for bar, value in zip(bars, values): ax_c.text(bar.get_x()+bar.get_width()/2, value+58, f"{value:,.0f}", ha="center", fontsize=6.7, fontweight="bold")
    ax_c.set_xticks(positions, labels); ax_c.set_ylabel("Year-held-out RMSE (kg ha$^{-1}$)")
    ax_c.set_ylim(0, max(values) * 1.18); ax_c.set_title("Adding imagery did not improve temporal prediction", loc="left", fontsize=8.4, fontweight="bold")
    ax_c.axvline(1.52, color="#BCC7CC", lw=0.7)
    ax_c.text(0.39, max(values) * 1.10, "1989--2025\nLandsat", ha="center", va="top", fontsize=6.4, color=COLORS["ink"])
    ax_c.text(3.43, max(values) * 1.10, "2017--2023\ndual-sensor", ha="center", va="top", fontsize=6.4, color=COLORS["ink"])
    ax_c.grid(axis="y", color="#E2E7E9", lw=0.45); panel_label(ax_c, "c")

    ax_d.hist(gains, bins=30, color="#D6DDE0", edgecolor="white")
    ax_d.axvline(0, color="#9BA8AE", lw=0.8, ls="--")
    ax_d.axvline(np.mean(gains), color=COLORS["rainfed"], lw=1.9)
    low, high = np.quantile(gains, [0.025, 0.975])
    ax_d.text(0.04, 0.93, f"MSE gain 95% interval\n[{low:,.0f}, {high:,.0f}]", transform=ax_d.transAxes, va="top", fontsize=7.0)
    ax_d.set_xlabel("MSE gain of Landsat vs management")
    ax_d.set_ylabel("Year-block bootstrap frequency")
    ax_d.set_title("No reliable predictive increment", loc="left", fontsize=8.4, fontweight="bold")
    panel_label(ax_d, "d")
    write_source("fig4_plot_level_remote_sensing_map.csv", mapped.drop(columns="geometry_wgs84"))
    write_source("fig4_remote_sensing_coverage.csv", coverage)
    write_source("fig4_strict_temporal_validation.csv", metrics)
    write_source("fig4_landsat_mse_gain_bootstrap.csv", pd.DataFrame({"mse_gain": gains}))
    save(fig, "Fig4_remote_sensing_integrity_and_negative_validation")


def main() -> None:
    data = load_rge()
    draw_fig1(data)
    draw_fig2(data)
    draw_fig3(data)
    draw_fig4()
    print(f"Wrote main figures to {FIGURES}")


if __name__ == "__main__":
    main()
