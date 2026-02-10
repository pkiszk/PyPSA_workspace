#!/usr/bin/env python3
"""
PSE API export CLI for wind/PV curtailment, production, and demand.

Pulls 15-minute data from:
- his-wlk-cal (wind, PV, demand)
- kse-load (load actual + forecast)
- poze-redoze (wind/PV curtailment: balance + network)

Outputs raw CSVs for each endpoint and a merged CSV keyed by dtime_utc.
Curtailment MW values are preserved, and MWh columns are added (MW * 0.25).

Example:
  python pse_export_cli.py --start-date 2024-01-01 --out-dir .
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable
import urllib.parse
import urllib.request

try:
    import pandas as pd
except ImportError:  # pragma: no cover - guard for environments without pandas
    pd = None


BASE_URL = "https://api.raporty.pse.pl/api"
DEFAULT_START_DATE = date(2024, 1, 1)
SLOT_HOURS = 0.25

HIS_COLUMNS = [
    "dtime_utc",
    "period_utc",
    "business_date",
    "wi",
    "pv",
    "demand",
]
KSE_COLUMNS = [
    "dtime_utc",
    "period_utc",
    "business_date",
    "load_actual",
    "load_fcst",
]
POZE_COLUMNS = [
    "dtime_utc",
    "period_utc",
    "business_date",
    "pv_red_balance",
    "pv_red_network",
    "wi_red_balance",
    "wi_red_network",
]

CURTAILMENT_COLUMNS = [
    "pv_red_balance",
    "pv_red_network",
    "wi_red_balance",
    "wi_red_network",
]
CURTAILMENT_TOTAL_COLUMNS = [
    "pv_red_total_mwh",
    "wi_red_total_mwh",
]

NUMERIC_COLUMNS = [
    "wi",
    "pv",
    "demand",
    "load_actual",
    "load_fcst",
    "wi_mwh",
    "pv_mwh",
    "pv_red_balance",
    "pv_red_network",
    "wi_red_balance",
    "wi_red_network",
    "pv_red_balance_mwh",
    "pv_red_network_mwh",
    "wi_red_balance_mwh",
    "wi_red_network_mwh",
    "pv_red_total_mwh",
    "wi_red_total_mwh",
]


@dataclass(frozen=True)
class FetchConfig:
    start_dt: datetime
    end_dt_exclusive: datetime
    page_size: int
    timeout_seconds: int


def parse_date_arg(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'. Expected format: YYYY-MM-DD."
        ) from exc


def default_end_date() -> date:
    return datetime.now(timezone.utc).date() - timedelta(days=1)


def format_dt(dt_value: datetime) -> str:
    return dt_value.strftime("%Y-%m-%d %H:%M:%S")


def build_filter(start_dt: datetime, end_dt_exclusive: datetime) -> str:
    start_str = format_dt(start_dt)
    end_str = format_dt(end_dt_exclusive)
    return f"dtime_utc ge '{start_str}' and dtime_utc lt '{end_str}'"


def encode_params(params: dict) -> str:
    return urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def fetch_json(url: str, params: dict | None, timeout_seconds: int) -> dict:
    if params:
        url = f"{url}?{encode_params(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "PSE-Export-CLI/1.0"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.load(response)


def fetch_all(endpoint: str, params: dict, timeout_seconds: int) -> list[dict]:
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    page = 0
    records: list[dict] = []
    next_url = url
    next_params = dict(params)

    while next_url:
        page += 1
        data = fetch_json(next_url, next_params, timeout_seconds)
        values = data.get("value", [])
        records.extend(values)
        next_url = data.get("nextLink")
        next_params = None
        print(f"[{endpoint}] page {page}: +{len(values)} records (total {len(records)})")

    return records


def normalize_dtime_utc(df: "pd.DataFrame", column: str = "dtime_utc") -> "pd.DataFrame":
    if column not in df.columns:
        raise KeyError(f"Missing '{column}' column.")
    dt_series = pd.to_datetime(df[column], errors="coerce")
    invalid = dt_series.isna()
    if invalid.any():
        dropped = int(invalid.sum())
        print(f"[warn] Dropping {dropped} rows with invalid {column} values.")
        df = df.loc[~invalid].copy()
        dt_series = dt_series.loc[~invalid]
    df[column] = dt_series.dt.strftime("%Y-%m-%d %H:%M:%S")
    df["Hour"] = dt_series.dt.hour
    df = df.sort_values(column).drop_duplicates(column, keep="last")
    return df


def coerce_numeric(df: "pd.DataFrame", columns: Iterable[str]) -> "pd.DataFrame":
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def add_curtailment_mwh(df: "pd.DataFrame") -> "pd.DataFrame":
    for col in CURTAILMENT_COLUMNS:
        if col in df.columns:
            df[f"{col}_mwh"] = df[col] * SLOT_HOURS
    if {"pv_red_balance_mwh", "pv_red_network_mwh"}.issubset(df.columns):
        df["pv_red_total_mwh"] = df["pv_red_balance_mwh"] + df["pv_red_network_mwh"]
    if {"wi_red_balance_mwh", "wi_red_network_mwh"}.issubset(df.columns):
        df["wi_red_total_mwh"] = df["wi_red_balance_mwh"] + df["wi_red_network_mwh"]
    return df


def add_generation_mwh(df: "pd.DataFrame") -> "pd.DataFrame":
    if "pv" in df.columns:
        df["pv_mwh"] = df["pv"] * SLOT_HOURS
    if "wi" in df.columns:
        df["wi_mwh"] = df["wi"] * SLOT_HOURS
    return df


def build_dataframe(records: list[dict], columns: list[str], numeric_cols: list[str]) -> "pd.DataFrame":
    if not records:
        return pd.DataFrame(columns=columns + ["Hour"])
    df = pd.DataFrame.from_records(records)
    keep_cols = [c for c in columns if c in df.columns]
    df = df.loc[:, keep_cols].copy()
    df = coerce_numeric(df, numeric_cols)
    df = normalize_dtime_utc(df)
    return df


def consolidate_columns(df: "pd.DataFrame", base: str, suffixes: Iterable[str]) -> "pd.DataFrame":
    columns = [base] + [f"{base}{suffix}" for suffix in suffixes]
    existing = [col for col in columns if col in df.columns]
    if not existing:
        return df
    combined = df[existing[0]]
    for col in existing[1:]:
        combined = combined.combine_first(df[col])
    df[base] = combined
    drop_cols = [col for col in existing if col != base]
    if drop_cols:
        df = df.drop(columns=drop_cols)
    return df


def merge_dataframes(
    his_df: "pd.DataFrame", kse_df: "pd.DataFrame", poze_df: "pd.DataFrame"
) -> "pd.DataFrame":
    merged = his_df.merge(kse_df, on="dtime_utc", how="outer", suffixes=("", "_kse"))
    merged = merged.merge(poze_df, on="dtime_utc", how="outer", suffixes=("", "_poze"))
    merged = consolidate_columns(merged, "period_utc", suffixes=("_kse", "_poze"))
    merged = consolidate_columns(merged, "business_date", suffixes=("_kse", "_poze"))
    merged = consolidate_columns(merged, "Hour", suffixes=("_kse", "_poze"))
    merged = coerce_numeric(merged, NUMERIC_COLUMNS)
    merged = merged.sort_values("dtime_utc")
    return merged


def run_export(config: FetchConfig, out_dir: Path) -> dict[str, Path]:
    filter_expr = build_filter(config.start_dt, config.end_dt_exclusive)
    common_params = {
        "$filter": filter_expr,
        "$orderby": "dtime_utc asc",
        "$first": config.page_size,
    }

    his_records = fetch_all(
        "his-wlk-cal",
        {**common_params, "$select": ",".join(HIS_COLUMNS)},
        config.timeout_seconds,
    )
    kse_records = fetch_all(
        "kse-load",
        {**common_params, "$select": ",".join(KSE_COLUMNS)},
        config.timeout_seconds,
    )
    poze_records = fetch_all(
        "poze-redoze",
        {**common_params, "$select": ",".join(POZE_COLUMNS)},
        config.timeout_seconds,
    )

    his_df = build_dataframe(his_records, HIS_COLUMNS, NUMERIC_COLUMNS)
    his_df = add_generation_mwh(his_df)
    kse_df = build_dataframe(kse_records, KSE_COLUMNS, NUMERIC_COLUMNS)
    poze_df = build_dataframe(poze_records, POZE_COLUMNS, NUMERIC_COLUMNS)
    poze_df = add_curtailment_mwh(poze_df)

    merged_df = merge_dataframes(his_df, kse_df, poze_df)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base_name = f"PSE_export_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "his-wlk-cal": out_dir / f"{base_name}_his-wlk-cal.csv",
        "kse-load": out_dir / f"{base_name}_kse-load.csv",
        "poze-redoze": out_dir / f"{base_name}_poze-redoze.csv",
        "merged": out_dir / f"{base_name}_merged.csv",
    }

    his_df.to_csv(paths["his-wlk-cal"], index=False)
    kse_df.to_csv(paths["kse-load"], index=False)
    poze_df.to_csv(paths["poze-redoze"], index=False)
    merged_df.to_csv(paths["merged"], index=False)

    return paths


def main() -> int:
    if pd is None:
        print("Error: pandas is required for this script. Please install pandas.", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(
        description="Export PSE 15-minute data (wind/PV production, demand, curtailment) to CSV."
    )
    parser.add_argument(
        "--start-date",
        type=parse_date_arg,
        default=DEFAULT_START_DATE,
        help="Start date (YYYY-MM-DD). Default: 2024-01-01.",
    )
    parser.add_argument(
        "--end-date",
        type=parse_date_arg,
        default=None,
        help="Inclusive end date (YYYY-MM-DD). Default: last full UTC day.",
    )
    parser.add_argument(
        "--out-dir",
        default=".",
        help="Output directory for CSV files (default: current directory).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=1000,
        help="Page size for API pagination (default: 1000).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="HTTP timeout per request in seconds (default: 60).",
    )

    args = parser.parse_args()

    end_date = args.end_date or default_end_date()
    if end_date < args.start_date:
        print("Error: end-date must be on or after start-date.", file=sys.stderr)
        return 2

    start_dt = datetime.combine(args.start_date, time.min)
    end_dt_exclusive = datetime.combine(end_date + timedelta(days=1), time.min)

    config = FetchConfig(
        start_dt=start_dt,
        end_dt_exclusive=end_dt_exclusive,
        page_size=max(1, args.page_size),
        timeout_seconds=max(1, args.timeout_seconds),
    )

    print(
        f"Pulling data from {format_dt(config.start_dt)} UTC "
        f"to {format_dt(config.end_dt_exclusive)} UTC (exclusive)."
    )

    out_dir = Path(args.out_dir)
    paths = run_export(config, out_dir)

    print("Export complete:")
    for key, path in paths.items():
        print(f"  {key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
