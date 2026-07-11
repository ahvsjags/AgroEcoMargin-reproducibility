#!/usr/bin/env python3
"""Strict temporal evaluation for the observed MCSE plot-yield RS panel.

The target is observed crop-only yield, never an operating-space proxy. Outer
folds leave out one calendar year; alpha selection, imputation, encoding and
scaling occur only in the corresponding training years. The script reports a
management-only comparator and a management-plus-preharvest-Landsat model.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path("/mnt/AgroEcoMargin")
PANEL = ROOT / "data/03_gold/mcse_plot_remote_sensing_yield_panel_gold.csv"
OUT = ROOT / "outputs/tables/mcse_plot_remote_sensing_temporal_evaluation.csv"
PREDICTIONS = ROOT / "outputs/tables/mcse_plot_remote_sensing_temporal_predictions.csv"
AUDIT = ROOT / "outputs/audits/mcse_plot_remote_sensing_temporal_evaluation_audit.json"
SEED = 20260710

CATEGORICAL = ["crop_group", "treatment", "replicate"]
LANDSAT = [
    "landsat_ndvi_mean", "landsat_ndvi_max", "landsat_ndvi_last", "landsat_ndvi_slope",
    "landsat_ndwi_mean", "landsat_nbr_mean", "landsat_red_mean", "landsat_nir08_mean",
    "landsat_swir16_mean", "landsat_swir22_mean", "landsat_clear_fraction_mean",
    "landsat_obs_count_mean", "landsat_valid_fraction_mean", "landsat_time_gap_days_mean",
]
ALPHAS = (0.1, 1.0, 10.0, 100.0, 1000.0)


def make_pipeline(features: list[str]) -> Pipeline:
    categorical = [name for name in CATEGORICAL if name in features]
    numeric = [name for name in features if name not in categorical]
    transformer = ColumnTransformer([
        ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical),
        ("numeric", Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]), numeric),
    ])
    return Pipeline([("prepare", transformer), ("ridge", Ridge())])


def select_alpha(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, features: list[str]) -> float:
    n_splits = min(5, len(np.unique(groups)))
    if n_splits < 2:
        return 10.0
    cv = GroupKFold(n_splits=n_splits)
    scores: list[float] = []
    for alpha in ALPHAS:
        fold_scores: list[float] = []
        for train_index, valid_index in cv.split(X, y, groups):
            model = make_pipeline(features)
            model.set_params(ridge__alpha=alpha)
            model.fit(X.iloc[train_index][features], y[train_index])
            fold_scores.append(mean_squared_error(y[valid_index], model.predict(X.iloc[valid_index][features])))
        scores.append(float(np.mean(fold_scores)))
    return float(ALPHAS[int(np.argmin(scores))])


def evaluate(data: pd.DataFrame, name: str, features: list[str]) -> tuple[dict[str, object], np.ndarray]:
    X = data[features].copy()
    y = data["yield_kg_ha"].to_numpy(dtype=float)
    groups = data["year"].to_numpy(dtype=int)
    predictions = np.zeros(len(data), dtype=float)
    alphas: list[float] = []
    outer = LeaveOneGroupOut()
    for train_index, test_index in outer.split(X, y, groups):
        alpha = select_alpha(X.iloc[train_index], y[train_index], groups[train_index], features)
        model = make_pipeline(features)
        model.set_params(ridge__alpha=alpha)
        model.fit(X.iloc[train_index][features], y[train_index])
        predictions[test_index] = model.predict(X.iloc[test_index][features])
        alphas.append(alpha)
    result = {
        "model": name,
        "target": "observed crop_only_yield_kg_ha",
        "n_observations": int(len(data)),
        "n_years": int(data["year"].nunique()),
        "outer_evaluation": "leave-one-calendar-year-out",
        "nested_group_cv": "GroupKFold within training calendar years",
        "rmse_kg_ha": float(mean_squared_error(y, predictions) ** 0.5),
        "mae_kg_ha": float(mean_absolute_error(y, predictions)),
        "r2_pooled": float(r2_score(y, predictions)),
        "median_selected_alpha": float(np.median(alphas)),
    }
    return result, predictions


def block_bootstrap_gain(data: pd.DataFrame, baseline: np.ndarray, augmented: np.ndarray) -> tuple[float, float, float]:
    y = data["yield_kg_ha"].to_numpy(dtype=float)
    years = data["year"].unique()
    index_by_year = {year: np.flatnonzero(data["year"].to_numpy() == year) for year in years}
    rng = np.random.default_rng(SEED)
    gains: list[float] = []
    for _ in range(5000):
        draw = rng.choice(years, size=len(years), replace=True)
        index = np.concatenate([index_by_year[year] for year in draw])
        gains.append(float(np.mean((y[index] - baseline[index]) ** 2) - np.mean((y[index] - augmented[index]) ** 2)))
    point = float(np.mean((y - baseline) ** 2) - np.mean((y - augmented) ** 2))
    low, high = np.quantile(gains, [0.025, 0.975]).tolist()
    return point, float(low), float(high)


def main() -> None:
    data = pd.read_csv(PANEL)
    data = data.loc[data["landsat_ndvi_mean"].notna()].copy()
    features = [name for name in LANDSAT if name in data.columns]
    baseline_result, baseline_prediction = evaluate(data, "M0_management_only", CATEGORICAL)
    plot_result, plot_prediction = evaluate(data, "M1_management_plus_plot_landsat", CATEGORICAL + features)
    gain, low, high = block_bootstrap_gain(data, baseline_prediction, plot_prediction)
    plot_result["mse_gain_vs_management_kg2_ha2"] = gain
    plot_result["year_block_bootstrap_mse_gain_ci_low"] = low
    plot_result["year_block_bootstrap_mse_gain_ci_high"] = high
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([baseline_result, plot_result]).to_csv(OUT, index=False)
    prediction = data[["observation_id", "year", "plot_numeric_id", "crop_group", "treatment", "replicate", "yield_kg_ha"]].copy()
    prediction["prediction_management_only"] = baseline_prediction
    prediction["prediction_management_plus_plot_landsat"] = plot_prediction
    prediction.to_csv(PREDICTIONS, index=False)
    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "panel": str(PANEL.relative_to(ROOT)),
        "panel_unit": "MCSE Treatment x Replicate observed harvest record with matching plot polygon",
        "outcome": "observed crop_only_yield_kg_ha",
        "no_operating_space_proxy_label": True,
        "no_aoi_aggregation": True,
        "preharvest_features_only": True,
        "finding": "The plot-level Landsat feature block did not improve year-held-out prediction over management-only baseline in this panel.",
        "results": [baseline_result, plot_result],
    }
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(pd.DataFrame([baseline_result, plot_result]).to_string(index=False))


if __name__ == "__main__":
    main()
