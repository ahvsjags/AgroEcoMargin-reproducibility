#!/usr/bin/env python3
"""Test whether experimental irrigation buffers the RGE N-by-weather slope.

This mechanism analysis uses the documented F1--F9 fertilizer schedule and
the same 27-year RGE panel as script 101. Its key quantity is the three-way
N x heat-dry stress x irrigation interaction. It is a within-experiment
mechanism check, not a replacement for randomized weather exposure.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("rge_base", HERE / "101_rebuild_rge_weather_n_inference.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load script 101.")
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)

OUT = BASE.OUT
SEED = 20260710
BOOTSTRAPS = 300
PERMUTATIONS = 600


def formula(stress: str, year_name: str) -> str:
    return (
        f"yield_kg_ha ~ C({year_name}) + C(plot) + C(crop_group):n100 + "
        f"n100:{stress} + n100:irrigated_binary + "
        f"n100:{stress}:irrigated_binary + n100:time_c"
    )


def fit(data: pd.DataFrame, stress: str, year_name: str = "year") -> tuple[object, str]:
    f = formula(stress, year_name)
    plain = smf.ols(f, data).fit()
    groups = data.loc[plain.model.data.row_labels, year_name]
    robust = smf.ols(f, data).fit(cov_type="cluster", cov_kwds={"groups": groups})
    return robust, f"n100:{stress}:irrigated_binary"


def bootstrap(data: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    years = np.array(sorted(data["year"].unique()))
    values: list[float] = []
    for _ in range(BOOTSTRAPS):
        blocks: list[pd.DataFrame] = []
        for index, year in enumerate(rng.choice(years, size=len(years), replace=True)):
            block = data.loc[data["year"].eq(year)].copy()
            block["year_boot"] = index
            blocks.append(block)
        sample = pd.concat(blocks, ignore_index=True)
        try:
            model = smf.ols(formula("heat_dry_stress_z", "year_boot"), sample).fit()
            values.append(float(model.params["n100:heat_dry_stress_z:irrigated_binary"]))
        except Exception:
            continue
    return np.asarray(values, dtype=float)


def permutation(data: pd.DataFrame, observed: float, rng: np.random.Generator) -> np.ndarray:
    annual = data.groupby("year")["heat_dry_stress_z"].first()
    years, values = annual.index.to_numpy(), annual.to_numpy()
    results: list[float] = []
    for _ in range(PERMUTATIONS):
        sample = data.copy()
        sample["permuted_stress"] = sample["year"].map(dict(zip(years, rng.permutation(values))))
        try:
            model, term = fit(sample, "permuted_stress")
            results.append(float(model.params[term]))
        except Exception:
            continue
    return np.asarray(results, dtype=float)


def concurrent_years(data: pd.DataFrame) -> np.ndarray:
    """Return years represented by both rainfed and irrigated gradients."""
    support = data.groupby(["year", "irrigated_binary"]).size().unstack(fill_value=0)
    return support.index[(support.get(0, 0) > 0) & (support.get(1, 0) > 0)].to_numpy()


def summarize(data: pd.DataFrame, analysis_scope: str) -> tuple[dict[str, object], np.ndarray, np.ndarray]:
    model, triple_term = fit(data, "heat_dry_stress_z")
    rainfed_term = "n100:heat_dry_stress_z"
    rng = np.random.default_rng(SEED)
    boot = bootstrap(data, rng)
    perm = permutation(data, float(model.params[triple_term]), rng)
    ci = model.conf_int()
    result: dict[str, object] = {
        "analysis_scope": analysis_scope,
        "n_rows": int(model.nobs),
        "n_years": int(data.loc[model.model.data.row_labels, "year"].nunique()),
        "n_plots": int(data.loc[model.model.data.row_labels, "plot"].nunique()),
        "rainfed_n_by_stress_effect_kg_ha_per_100kgN_per_1sd": float(model.params[rainfed_term]),
        "rainfed_cluster_ci_low": float(ci.loc[rainfed_term].iloc[0]),
        "rainfed_cluster_ci_high": float(ci.loc[rainfed_term].iloc[1]),
        "irrigation_buffering_interaction_kg_ha_per_100kgN_per_1sd": float(model.params[triple_term]),
        "buffer_cluster_ci_low": float(ci.loc[triple_term].iloc[0]),
        "buffer_cluster_ci_high": float(ci.loc[triple_term].iloc[1]),
        "buffer_year_block_bootstrap_ci_low": float(np.quantile(boot, 0.025)),
        "buffer_year_block_bootstrap_ci_high": float(np.quantile(boot, 0.975)),
        "buffer_year_label_permutation_p_two_sided": float((1 + np.sum(np.abs(perm) >= abs(model.params[triple_term]))) / (1 + len(perm))),
        "interpretation": "Mechanism-consistent irrigation buffering with annual-resampling uncertainty; not final causal proof.",
    }
    return result, boot, perm


def main() -> None:
    data = BASE.read_rge()
    all_result, all_boot, all_perm = summarize(data, "All available years (1999-2025; irrigation begins in 2003)")
    shared_years = concurrent_years(data)
    paired = data.loc[data["year"].isin(shared_years)].copy()
    paired_result, paired_boot, paired_perm = summarize(paired, "Concurrent rainfed-irrigated years (2003-2025)")
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([all_result]).to_csv(OUT / "rge_irrigation_weather_n_mechanism_summary.csv", index=False)
    pd.DataFrame({"bootstrap_buffering_interaction": all_boot}).to_csv(OUT / "rge_irrigation_weather_n_mechanism_bootstrap.csv", index=False)
    pd.DataFrame({"permuted_buffering_interaction": all_perm}).to_csv(OUT / "rge_irrigation_weather_n_mechanism_permutation.csv", index=False)
    pd.DataFrame([paired_result]).to_csv(OUT / "rge_irrigation_weather_n_mechanism_paired_years_summary.csv", index=False)
    pd.DataFrame({"bootstrap_buffering_interaction": paired_boot}).to_csv(OUT / "rge_irrigation_weather_n_mechanism_paired_years_bootstrap.csv", index=False)
    pd.DataFrame({"permuted_buffering_interaction": paired_perm}).to_csv(OUT / "rge_irrigation_weather_n_mechanism_paired_years_permutation.csv", index=False)
    print(pd.DataFrame([all_result, paired_result]).to_string(index=False))


if __name__ == "__main__":
    main()
