#!/usr/bin/env python3
"""Additional submission diagnostics for the Agriculture manuscript.

This script deliberately leaves the prespecified primary analyses unchanged.
It adds finite-year robustness diagnostics, documents crop/year support, and
exports fully nested outer-year remote-sensing diagnostics for the supplement.
"""

from __future__ import annotations

import importlib.util
import itertools
import math
import argparse
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("rge_base", HERE / "101_rebuild_rge_weather_n_inference.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load the prespecified RGE analysis module.")
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)

WORK = HERE.parents[1]
RESULTS = WORK / "analysis_outputs"
OUT = RESULTS / "submission_revision"
FIGURES = RESULTS / "extended_data_v7_integrity_rebuild"
SOURCE = RESULTS / "figure_source_data_v7"
PANEL = WORK / "analysis_inputs" / "remote_sensing_rebuilt" / "mcse_plot_remote_sensing_yield_panel_gold.csv"
SEED = 20260711
STRESS = "heat_dry_stress_z"
CATEGORICAL = ["crop_group", "treatment", "replicate"]
LANDSAT = [
    "landsat_ndvi_mean", "landsat_ndvi_max", "landsat_ndvi_last", "landsat_ndvi_slope",
    "landsat_ndwi_mean", "landsat_nbr_mean", "landsat_red_mean", "landsat_nir08_mean",
    "landsat_swir16_mean", "landsat_swir22_mean", "landsat_clear_fraction_mean",
    "landsat_obs_count_mean", "landsat_valid_fraction_mean", "landsat_time_gap_days_mean",
]
ALPHAS = (0.1, 1.0, 10.0, 100.0, 1000.0)

mpl.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8, "axes.linewidth": 0.65,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6,
})


def export_figure(fig: plt.Figure, stem: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    for suffix, kwargs in {"png": {"dpi": 600}, "tiff": {"dpi": 600}, "pdf": {}, "svg": {}}.items():
        fig.savefig(FIGURES / f"{stem}.{suffix}", bbox_inches="tight", facecolor="white", **kwargs)
    plt.close(fig)


def model_formula(include_stress: bool = True) -> str:
    interaction = f" + n100:{STRESS}" if include_stress else ""
    return f"yield_kg_ha ~ C(year) + C(plot) + C(crop_group):n100{interaction} + n100:time_c"


def robust_fit(data: pd.DataFrame, include_stress: bool = True):
    formula = model_formula(include_stress)
    plain = smf.ols(formula, data).fit()
    groups = data.loc[plain.model.data.row_labels, "year"]
    return smf.ols(formula, data).fit(cov_type="cluster", cov_kwds={"groups": groups})


def crop_year_support(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (year, crop), frame in data.groupby(["year", "crop_group"], observed=True):
        rows.append({
            "year": int(year), "crop_group": crop, "n_records": int(len(frame)),
            "n_plots": int(frame["plot"].nunique()),
            "n_nitrogen_rates": int(frame["fertilizer_rate_kg_ha"].nunique()),
            "nitrogen_min_kg_ha": float(frame["fertilizer_rate_kg_ha"].min()),
            "nitrogen_max_kg_ha": float(frame["fertilizer_rate_kg_ha"].max()),
        })
    return pd.DataFrame(rows).sort_values(["year", "crop_group"]).reset_index(drop=True)


def leave_two_years(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    years = sorted(data["year"].unique())
    for y1, y2 in itertools.combinations(years, 2):
        # This is a coefficient-stability screen; cluster intervals are
        # reported for the primary model, not re-estimated 351 times here.
        model = smf.ols(model_formula(include_stress=True), data.loc[~data["year"].isin([y1, y2])].copy()).fit()
        rows.append({
            "excluded_year_1": int(y1), "excluded_year_2": int(y2),
            "effect_kg_ha_per_100kgN_per_1sd": float(model.params[f"n100:{STRESS}"]),
        })
    return pd.DataFrame(rows)


def wild_cluster_test(data: pd.DataFrame, draws: int = 999) -> pd.DataFrame:
    """Rademacher wild-year bootstrap test of the N-by-stress coefficient."""
    unrestricted = robust_fit(data, include_stress=True)
    term = f"n100:{STRESS}"
    observed_t = float(unrestricted.tvalues[term])
    restricted = smf.ols(model_formula(include_stress=False), data).fit()
    fitted = restricted.fittedvalues.to_numpy()
    residual = restricted.resid.to_numpy()
    years = data.loc[restricted.model.data.row_labels, "year"].to_numpy()
    rng = np.random.default_rng(SEED)
    values = []
    for draw in range(draws):
        signs = {year: rng.choice([-1.0, 1.0]) for year in np.unique(years)}
        sample = data.copy()
        sample["yield_kg_ha"] = fitted + residual * np.array([signs[year] for year in years])
        fitted_model = robust_fit(sample, include_stress=True)
        values.append({"draw": draw + 1, "wild_t": float(fitted_model.tvalues[term]), "wild_effect": float(fitted_model.params[term])})
    output = pd.DataFrame(values)
    output["observed_t"] = observed_t
    output["wild_two_sided_p"] = (1 + int((output["wild_t"].abs() >= abs(observed_t)).sum())) / (1 + len(output))
    return output


def make_pipeline(features: list[str]) -> Pipeline:
    categorical = [feature for feature in CATEGORICAL if feature in features]
    numerical = [feature for feature in features if feature not in categorical]
    prep = ColumnTransformer([
        ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical),
        ("numerical", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numerical),
    ])
    return Pipeline([("prepare", prep), ("ridge", Ridge())])


def select_alpha(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, features: list[str]) -> float:
    n_splits = min(5, len(np.unique(groups)))
    if n_splits < 2:
        return 10.0
    values = []
    for alpha in ALPHAS:
        scores = []
        for train, test in GroupKFold(n_splits=n_splits).split(X, y, groups):
            fitted = make_pipeline(features).set_params(ridge__alpha=alpha)
            fitted.fit(X.iloc[train][features], y[train])
            scores.append(mean_squared_error(y[test], fitted.predict(X.iloc[test][features])))
        values.append(float(np.mean(scores)))
    return float(ALPHAS[int(np.argmin(values))])


def nested_remote_diagnostics(outer_years: set[int] | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    data = pd.read_csv(PANEL)
    data = data.loc[data["landsat_ndvi_mean"].notna()].copy().reset_index(drop=True)
    y = data["yield_kg_ha"].to_numpy(float)
    groups = data["year"].to_numpy(int)
    models = {
        "management_only": CATEGORICAL,
        "management_plus_landsat": CATEGORICAL + [name for name in LANDSAT if name in data.columns],
    }
    predictions: list[pd.DataFrame] = []
    alpha_rows: list[dict[str, object]] = []
    for name, features in models.items():
        values = np.full(len(data), np.nan)
        for train, test in LeaveOneGroupOut().split(data[features], y, groups):
            held_out_year = int(groups[test][0])
            if outer_years is not None and held_out_year not in outer_years:
                continue
            alpha = select_alpha(data.iloc[train][features], y[train], groups[train], features)
            fitted = make_pipeline(features).set_params(ridge__alpha=alpha)
            fitted.fit(data.iloc[train][features], y[train])
            values[test] = fitted.predict(data.iloc[test][features])
            alpha_rows.append({"model": name, "outer_year": held_out_year, "selected_alpha": alpha, "n_train": int(len(train)), "n_test": int(len(test))})
        keep = np.isfinite(values)
        output = data.loc[keep, ["observation_id", "year", "crop_group", "treatment", "replicate", "yield_kg_ha"]].copy()
        output["model"] = name
        output["prediction_kg_ha"] = values[keep]
        output["residual_kg_ha"] = output["prediction_kg_ha"] - output["yield_kg_ha"]
        predictions.append(output)
    pred = pd.concat(predictions, ignore_index=True)
    metrics = []
    for (name, year), frame in pred.groupby(["model", "year"], observed=True):
        observed = frame["yield_kg_ha"].to_numpy(float)
        estimated = frame["prediction_kg_ha"].to_numpy(float)
        metrics.append({
            "model": name, "outer_year": int(year), "n_test": int(len(frame)),
            "rmse_kg_ha": float(math.sqrt(mean_squared_error(observed, estimated))),
            "mae_kg_ha": float(mean_absolute_error(observed, estimated)),
            "r2_outer_year": float(r2_score(observed, estimated)) if len(frame) > 1 else np.nan,
        })
    return pd.DataFrame(metrics), pred, pd.DataFrame(alpha_rows)


def plot_robustness(support: pd.DataFrame, leave2: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(7.1, 5.7), constrained_layout=True)
    palette = {"corn": "#D28B2A", "soybean": "#4A8C5B", "wheat": "#7D6AA7"}
    ax = axes[0, 0]
    for crop, frame in support.groupby("crop_group", observed=True):
        ax.scatter(frame["year"], [crop] * len(frame), s=frame["n_records"] * 1.3, color=palette.get(crop, "#777777"), alpha=0.85, edgecolor="white", linewidth=0.4)
    ax.set(title="a  Crop-year support", xlabel="Harvest year", ylabel="Crop group", xlim=(1998, 2026))
    ax.grid(axis="x", color="#E6E6E6", lw=0.5)
    ax = axes[0, 1]
    ax.hist(leave2["effect_kg_ha_per_100kgN_per_1sd"], bins=22, color="#6A8EAE", ec="white")
    ax.axvline(0, color="#555555", lw=0.8); ax.axvline(-254.6, color="#A7443A", lw=1.1)
    ax.set(title="b  Leave-two-year-out estimates", xlabel="N × heat-dry coefficient (kg ha$^{-1}$)", ylabel="Combinations (n = 351)")
    ax = axes[1, 0]
    ordered = leave2.sort_values("effect_kg_ha_per_100kgN_per_1sd").reset_index(drop=True)
    ax.plot(np.arange(1, len(ordered) + 1), ordered["effect_kg_ha_per_100kgN_per_1sd"], color="#6A8EAE", lw=1.0)
    ax.axhline(0, color="#555555", lw=0.8)
    ax.axhline(-254.6, color="#A7443A", lw=1.1, label="Primary estimate")
    ax.legend(frameon=False, fontsize=7)
    ax.set(title="c  Ordered finite-year stability", xlabel="Leave-two-year-out combination", ylabel="N × heat-dry coefficient (kg ha$^{-1}$)")
    ax = axes[1, 1]
    years = support.groupby("crop_group", observed=True)["year"].nunique().reindex(["corn", "soybean", "wheat"])
    plots = support.groupby("crop_group", observed=True)["n_plots"].max().reindex(years.index)
    x = np.arange(len(years)); width = 0.37
    ax.bar(x - width / 2, years, width, color="#5F86A4", label="Years")
    ax.bar(x + width / 2, plots, width, color="#D7A04B", label="Plots in a crop-year")
    ax.set_xticks(x, years.index); ax.set(title="d  Panel support by crop", ylabel="Count")
    ax.legend(frameon=False, fontsize=7)
    for axis in axes.ravel():
        axis.spines[["top", "right"]].set_visible(False)
    export_figure(fig, "ExtendedData_Fig8_crop_year_and_finite_year_robustness")


def plot_remote(metrics: pd.DataFrame, predictions: pd.DataFrame, alphas: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(7.1, 5.7), constrained_layout=True)
    colors = {"management_only": "#607D9B", "management_plus_landsat": "#B44A3A"}
    labels = {"management_only": "Management only", "management_plus_landsat": "Management + Landsat"}
    ax = axes[0, 0]
    for name, frame in metrics.groupby("model", observed=True):
        frame = frame.sort_values("outer_year")
        ax.plot(frame["outer_year"], frame["rmse_kg_ha"], marker="o", ms=3.1, lw=1.0, color=colors[name], label=labels[name])
    ax.set(title="a  Outer-year RMSE", xlabel="Held-out calendar year", ylabel="RMSE (kg ha$^{-1}$)")
    ax.legend(frameon=False, fontsize=6.7); ax.spines[["top", "right"]].set_visible(False)
    for name, axis in [("management_only", axes[0, 1]), ("management_plus_landsat", axes[1, 0])]:
        frame = predictions.loc[predictions["model"].eq(name)]
        axis.scatter(frame["yield_kg_ha"], frame["prediction_kg_ha"], s=9, alpha=0.5, color=colors[name], edgecolor="none")
        lo = min(frame["yield_kg_ha"].min(), frame["prediction_kg_ha"].min()); hi = max(frame["yield_kg_ha"].max(), frame["prediction_kg_ha"].max())
        axis.plot([lo, hi], [lo, hi], color="#4F4F4F", lw=0.75, ls="--")
        axis.set(title=("b  " if name == "management_only" else "c  ") + labels[name], xlabel="Observed yield (kg ha$^{-1}$)", ylabel="Outer prediction (kg ha$^{-1}$)")
        axis.spines[["top", "right"]].set_visible(False)
    ax = axes[1, 1]
    for name, frame in alphas.groupby("model", observed=True):
        frame = frame.sort_values("outer_year")
        ax.scatter(frame["outer_year"], frame["selected_alpha"], s=15, color=colors[name], label=labels[name], alpha=0.8)
    ax.set_yscale("log"); ax.set(title="d  Inner-CV ridge penalties", xlabel="Held-out calendar year", ylabel="Selected alpha")
    ax.legend(frameon=False, fontsize=6.7); ax.spines[["top", "right"]].set_visible(False)
    export_figure(fig, "ExtendedData_Fig9_remote_outer_year_diagnostics")


def write_csvs(folder: Path, metrics: pd.DataFrame, predictions: pd.DataFrame, alphas: pd.DataFrame) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(folder / "remote_outer_year_metrics.csv", index=False)
    predictions.to_csv(folder / "remote_outer_predictions.csv", index=False)
    alphas.to_csv(folder / "remote_outer_alphas.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crop-only", action="store_true", help="Run crop/year and leave-two-year diagnostics only.")
    parser.add_argument("--remote-year", type=int, help="Run one outer remote-sensing year and save a durable chunk.")
    parser.add_argument("--assemble-remote", action="store_true", help="Assemble remote chunks and render the diagnostic figure.")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True); SOURCE.mkdir(parents=True, exist_ok=True)
    chunks = OUT / "remote_year_chunks"
    if args.remote_year is not None:
        metrics, predictions, alphas = nested_remote_diagnostics({args.remote_year})
        if metrics.empty:
            raise ValueError(f"No Landsat panel rows found for outer year {args.remote_year}.")
        write_csvs(chunks / str(args.remote_year), metrics, predictions, alphas)
        print(f"Saved remote outer-year chunk {args.remote_year}.")
        return
    if args.assemble_remote:
        metric_files = sorted(chunks.glob("*/remote_outer_year_metrics.csv"))
        if not metric_files:
            raise FileNotFoundError("No remote outer-year chunks were found.")
        metrics = pd.concat([pd.read_csv(path) for path in metric_files], ignore_index=True)
        predictions = pd.concat([pd.read_csv(path.parent / "remote_outer_predictions.csv") for path in metric_files], ignore_index=True)
        alphas = pd.concat([pd.read_csv(path.parent / "remote_outer_alphas.csv") for path in metric_files], ignore_index=True)
        if metrics.duplicated(["model", "outer_year"]).any():
            raise ValueError("Duplicate outer-year chunks detected.")
        for folder in (OUT, SOURCE):
            write_csvs(folder, metrics, predictions, alphas)
        plot_remote(metrics, predictions, alphas)
        print(f"Assembled {metrics.outer_year.nunique()} outer years.")
        return
    rainfed = BASE.read_rge().loc[lambda frame: frame["irrigated_binary"].eq(0)].copy()
    support = crop_year_support(rainfed)
    leave2 = leave_two_years(rainfed)
    for folder in (OUT, SOURCE):
        support.to_csv(folder / "crop_year_support.csv", index=False)
        leave2.to_csv(folder / "leave_two_year_out.csv", index=False)
    plot_robustness(support, leave2)
    print("Crop/year support:\n", support.groupby("crop_group").agg(years=("year", "nunique"), records=("n_records", "sum")).to_string())
    print("Leave-two-year-out coefficient range:", leave2.effect_kg_ha_per_100kgN_per_1sd.min(), leave2.effect_kg_ha_per_100kgN_per_1sd.max())
    if not args.crop_only:
        print("Crop/year diagnostics complete. Run --remote-year for each outer year, then --assemble-remote.")


if __name__ == "__main__":
    main()
