#!/usr/bin/env python3
"""Build a leakage-guarded MCSE plot-level remote-sensing yield panel.

Unlike the retired AOI/operating-space panel, every record here joins an
observed MCSE Treatment x Replicate harvest yield to the matching Gold-cube
plot polygon. Spectral summaries stop at the calendar half-month immediately
before the recorded harvest date. This is a source-data builder only: it does
not estimate model accuracy or fabricate a risk label.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import zarr


ROOT = Path("/mnt/AgroEcoMargin")
YIELDS = ROOT / "data_acquisition/downloads/kbs_lter/mcse/yields/051_agronomic_yields_of_annual_crops/051_agronomic_yields_of_annual_crops.csv"
CROSSWALK = ROOT / "data/02_silver/remote_sensing_plot_support/kbs_plot_id_crosswalk.csv"
CUBES = {
    "landsat": ROOT / "data/03_gold/kbs_landsat_cube.zarr",
    "sentinel2": ROOT / "data/03_gold/kbs_s2_cube.zarr",
}
OUT = ROOT / "data/03_gold/mcse_plot_remote_sensing_yield_panel_gold.csv"
AUDIT = ROOT / "outputs/audits/mcse_plot_remote_sensing_yield_panel_audit.json"

BANDS = ("blue", "green", "red", "nir08", "swir16", "swir22")


def read_noncomment_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        lines = (line for line in handle if line.strip() and not line.startswith("#"))
        return list(csv.DictReader(lines))


def as_float(value: str | None) -> float | None:
    try:
        value = float(str(value))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def harvest_step(value: str) -> int | None:
    """Map an observed harvest date to the preceding 24-step calendar slot."""
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            stamp = datetime.strptime(value[:10], "%Y-%m-%d")
        except ValueError:
            return None
    step = (stamp.month - 1) * 2 + (1 if stamp.day <= 15 else 2)
    return max(1, min(24, step - 1))


def crop_group(value: str) -> str:
    name = value.lower()
    if "zea" in name or "corn" in name or "maize" in name:
        return "corn"
    if "triticum" in name or "wheat" in name:
        return "wheat"
    if "glycine" in name or "soy" in name:
        return "soybean"
    return "other"


def mean_or_blank(values: list[float]) -> float | str:
    values = [value for value in values if math.isfinite(value)]
    return round(float(np.mean(values)), 7) if values else ""


def build_cube_cache(cube_path: Path) -> tuple[dict[int, list[tuple[np.ndarray, np.ndarray]]], np.ndarray, dict[int, int]]:
    cube = zarr.open_group(str(cube_path), mode="r")
    plot_ids = np.asarray(cube["plot_id_mask"][:], dtype=np.int32)
    locations: dict[int, list[tuple[np.ndarray, np.ndarray]]] = {}
    for plot_id in sorted(int(v) for v in np.unique(plot_ids) if int(v) > 0):
        locations[plot_id] = list(zip(*np.where(plot_ids == plot_id)))
    years = np.asarray(cube["year"][:], dtype=np.int32)
    year_index = {int(year): index for index, year in enumerate(years)}
    return locations, years, year_index


def step_summary(cube: zarr.hierarchy.Group, year_index: int, step_index: int, locations: dict[int, list[tuple[np.ndarray, np.ndarray]]]) -> dict[int, dict[str, float]]:
    reflectance = np.asarray(cube["reflectance"][year_index, step_index, :, :, :], dtype=np.float32)
    clear = np.asarray(cube["clear_fraction"][year_index, step_index, :, :], dtype=np.float32)
    obs = np.asarray(cube["obs_count"][year_index, step_index, :, :], dtype=np.float32)
    valid = np.asarray(cube["valid_mask"][year_index, step_index, :, :], dtype=np.uint8)
    gap = float(cube["time_gap_days"][year_index, step_index])
    result: dict[int, dict[str, float]] = {}
    for plot_id, coords in locations.items():
        rows = np.fromiter((item[0] for item in coords), dtype=np.intp)
        cols = np.fromiter((item[1] for item in coords), dtype=np.intp)
        pixels = reflectance[:, rows, cols]
        usable = np.all(pixels > -100, axis=0) & (valid[rows, cols] > 0)
        if not np.any(usable):
            continue
        data = pixels[:, usable]
        red, nir, swir16, swir22 = data[2], data[3], data[4], data[5]
        with np.errstate(divide="ignore", invalid="ignore"):
            ndvi = (nir - red) / (nir + red)
            ndwi = (nir - swir16) / (nir + swir16)
            nbr = (nir - swir22) / (nir + swir22)
        summary = {band: float(np.mean(data[index])) for index, band in enumerate(BANDS)}
        summary.update({
            "ndvi": float(np.nanmean(ndvi)),
            "ndwi": float(np.nanmean(ndwi)),
            "nbr": float(np.nanmean(nbr)),
            "clear_fraction": float(np.mean(clear[rows, cols][usable])),
            "obs_count": float(np.mean(obs[rows, cols][usable])),
            "valid_fraction": float(np.mean(usable)),
            "time_gap_days": gap if gap > -9000 else math.nan,
            "pixels_used": float(np.sum(usable)),
        })
        result[plot_id] = summary
    return result


def extract_sensor_features(sensor: str, cube_path: Path, needs: dict[tuple[int, int], int]) -> dict[tuple[int, int], dict[str, float]]:
    cube = zarr.open_group(str(cube_path), mode="r")
    locations, _, year_index = build_cube_cache(cube_path)
    by_year: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for (year, plot_id), max_step in needs.items():
        if year in year_index and plot_id in locations:
            by_year[year].append((plot_id, max_step))
    output: dict[tuple[int, int], dict[str, float]] = {}
    for year, requested in sorted(by_year.items()):
        per_plot_steps: dict[int, list[dict[str, float]]] = defaultdict(list)
        maximum = max(max_step for _, max_step in requested)
        for step in range(maximum):
            summaries = step_summary(cube, year_index[year], step, locations)
            for plot_id, max_step in requested:
                if step < max_step and plot_id in summaries:
                    per_plot_steps[plot_id].append(summaries[plot_id])
        for plot_id, max_step in requested:
            records = per_plot_steps.get(plot_id, [])
            if not records:
                continue
            values: dict[str, float] = {"available_steps": float(len(records)), "max_step": float(max_step)}
            for field in (*BANDS, "ndvi", "ndwi", "nbr", "clear_fraction", "obs_count", "valid_fraction", "time_gap_days", "pixels_used"):
                series = [record[field] for record in records if math.isfinite(record[field])]
                if not series:
                    continue
                values[f"{field}_mean"] = float(np.mean(series))
                values[f"{field}_max"] = float(np.max(series))
                values[f"{field}_last"] = float(series[-1])
            ndvi = [record["ndvi"] for record in records if math.isfinite(record["ndvi"])]
            if len(ndvi) >= 2:
                values["ndvi_slope"] = float((ndvi[-1] - ndvi[0]) / (len(ndvi) - 1))
            output[(year, plot_id)] = values
    return output


def main() -> None:
    crosswalk_rows = read_noncomment_csv(CROSSWALK)
    crosswalk = {(row["treatment"].strip(), row["replicate"].strip()): int(row["plot_numeric_id"]) for row in crosswalk_rows}
    raw_yields = read_noncomment_csv(YIELDS)
    observations: list[dict[str, object]] = []
    for row in raw_yields:
        year = int(float(row["Year"])) if row.get("Year") else None
        plot_id = crosswalk.get((row.get("Treatment", "").strip(), row.get("Replicate", "").strip()))
        yield_value = as_float(row.get("crop_only_yield_kg_ha"))
        max_step = harvest_step(row.get("Date", ""))
        if year is None or plot_id is None or yield_value is None or max_step is None:
            continue
        observations.append({
            "year": year, "plot_numeric_id": plot_id, "treatment": row["Treatment"].strip(),
            "replicate": row["Replicate"].strip(), "crop_raw": row.get("Crop", ""),
            "crop_group": crop_group(row.get("Crop", "")), "harvest_date": row.get("Date", ""),
            "preharvest_step_max": max_step, "yield_kg_ha": yield_value,
            "whole_plot_yield_kg_ha": as_float(row.get("whole_plot_yield_kg_ha")),
        })
    needs = {(int(row["year"]), int(row["plot_numeric_id"])): int(row["preharvest_step_max"]) for row in observations}
    sensor_features = {sensor: extract_sensor_features(sensor, cube_path, needs) for sensor, cube_path in CUBES.items()}
    fields = [
        "observation_id", "year", "plot_numeric_id", "treatment", "replicate", "crop_raw", "crop_group",
        "harvest_date", "preharvest_step_max", "yield_kg_ha", "whole_plot_yield_kg_ha", "feature_scope",
    ]
    feature_fields = [
        "available_steps", "max_step", *[f"{field}_{stat}" for field in (*BANDS, "ndvi", "ndwi", "nbr", "clear_fraction", "obs_count", "valid_fraction", "time_gap_days", "pixels_used") for stat in ("mean", "max", "last")], "ndvi_slope",
    ]
    fields.extend(f"{sensor}_{field}" for sensor in CUBES for field in feature_fields)
    output: list[dict[str, object]] = []
    for index, row in enumerate(observations, start=1):
        base = dict(row)
        base["observation_id"] = f"mcse_rs_yield_{index:06d}"
        covered = []
        for sensor in CUBES:
            values = sensor_features[sensor].get((int(row["year"]), int(row["plot_numeric_id"])), {})
            if values:
                covered.append(sensor)
            for field in feature_fields:
                value = values.get(field, "")
                base[f"{sensor}_{field}"] = round(value, 7) if isinstance(value, float) and math.isfinite(value) else ""
        base["feature_scope"] = "+".join(covered) if covered else "none"
        output.append(base)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output)
    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_yield_table": str(YIELDS.relative_to(ROOT)),
        "crosswalk": str(CROSSWALK.relative_to(ROOT)),
        "unit": "observed MCSE Treatment x Replicate harvest record",
        "target": "observed crop_only_yield_kg_ha",
        "preharvest_rule": "features include only calendar slots ending before the recorded harvest half-month",
        "observations_with_plot_geometry": len(observations),
        "feature_coverage": {sensor: sum(1 for row in output if str(row["feature_scope"]) and sensor in str(row["feature_scope"])) for sensor in CUBES},
        "no_proxy_label": True,
        "no_aoi_aggregation": True,
        "output": str(OUT.relative_to(ROOT)),
    }
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
