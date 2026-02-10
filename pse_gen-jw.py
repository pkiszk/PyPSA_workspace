#!/usr/bin/env python3
"""
PSE API export CLI for per-unit generation (gen-jw).

Pulls 15-minute per-generating-unit data from:
- gen-jw (generation per unit: power plant, resource code, operating mode, value)

Outputs a single CSV with all fields as returned by the API.

Example:
  python pse_gen-jw.py --start-date 2024-01-01 --out-dir .
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None


BASE_URL = "https://api.raporty.pse.pl/api"
DEFAULT_START_DATE = date(2024, 1, 1)
DEFAULT_CHUNK_HOURS = 6
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 1.0

GEN_JW_COLUMNS = [
    "dtime_utc",
    "period_utc",
    "business_date",
    "dtime",
    "period",
    "power_plant",
    "resource_code",
    "operating_mode",
    "operating_mode_eng",
    "wartosc",
    "publication_ts",
    "publication_ts_utc",
]


@dataclass(frozen=True)
class FetchConfig:
    start_dt: datetime
    end_dt_exclusive: datetime
    page_size: int
    timeout_seconds: int
    chunk_hours: int


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


def fetch_json(
    url: str,
    params: dict | None,
    timeout_seconds: int,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
) -> dict:
    if params:
        url = f"{url}?{encode_params(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "PSE-Export-CLI/1.0"})
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code >= 500 and attempt < max_retries:
                wait = backoff_seconds * (2**attempt)
                print(f"[warn] HTTP {exc.code}; retrying in {wait:.1f}s ({attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            raise
        except URLError as exc:
            if attempt < max_retries:
                wait = backoff_seconds * (2**attempt)
                print(f"[warn] Network error: {exc}; retrying in {wait:.1f}s ({attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            raise


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


def iter_time_chunks(start_dt: datetime, end_dt_exclusive: datetime, chunk_hours: int):
    if chunk_hours <= 0:
        raise ValueError("chunk_hours must be > 0")
    step = timedelta(hours=chunk_hours)
    current = start_dt
    while current < end_dt_exclusive:
        chunk_end = min(current + step, end_dt_exclusive)
        yield current, chunk_end
        current = chunk_end


def fetch_all_chunked(
    endpoint: str,
    base_params: dict,
    start_dt: datetime,
    end_dt_exclusive: datetime,
    timeout_seconds: int,
    chunk_hours: int,
) -> list[dict]:
    records: list[dict] = []
    for chunk_start, chunk_end in iter_time_chunks(start_dt, end_dt_exclusive, chunk_hours):
        filter_expr = build_filter(chunk_start, chunk_end)
        params = {**base_params, "$filter": filter_expr}
        print(
            f"[{endpoint}] chunk {format_dt(chunk_start)} to {format_dt(chunk_end)} UTC"
        )
        chunk_records = fetch_all(endpoint, params, timeout_seconds)
        records.extend(chunk_records)
    return records


def build_dataframe(records: list[dict]) -> "pd.DataFrame":
    if not records:
        return pd.DataFrame(columns=GEN_JW_COLUMNS)
    df = pd.DataFrame.from_records(records)
    keep_cols = [c for c in GEN_JW_COLUMNS if c in df.columns]
    df = df.loc[:, keep_cols].copy()

    # Normalize dtime_utc to a consistent format
    dt_series = pd.to_datetime(df["dtime_utc"], errors="coerce")
    invalid = dt_series.isna()
    if invalid.any():
        print(f"[warn] Dropping {int(invalid.sum())} rows with invalid dtime_utc values.")
        df = df.loc[~invalid].copy()
        dt_series = dt_series.loc[~invalid]
    df["dtime_utc"] = dt_series.dt.strftime("%Y-%m-%d %H:%M:%S")

    df["wartosc"] = pd.to_numeric(df["wartosc"], errors="coerce")

    df = df.sort_values(["dtime_utc", "resource_code"]).reset_index(drop=True)
    return df


def run_export(config: FetchConfig, out_dir: Path) -> Path:
    base_params = {
        "$orderby": "dtime_utc asc",
        "$first": config.page_size,
        "$select": ",".join(GEN_JW_COLUMNS),
    }

    span_hours = (config.end_dt_exclusive - config.start_dt).total_seconds() / 3600
    if config.chunk_hours > 0 and span_hours > config.chunk_hours:
        records = fetch_all_chunked(
            "gen-jw",
            base_params,
            config.start_dt,
            config.end_dt_exclusive,
            config.timeout_seconds,
            config.chunk_hours,
        )
    else:
        filter_expr = build_filter(config.start_dt, config.end_dt_exclusive)
        params = {**base_params, "$filter": filter_expr}
        try:
            records = fetch_all("gen-jw", params, config.timeout_seconds)
        except HTTPError as exc:
            if exc.code >= 500 and config.chunk_hours > 0:
                print("[warn] Server error; retrying with chunked fetch.")
                records = fetch_all_chunked(
                    "gen-jw",
                    base_params,
                    config.start_dt,
                    config.end_dt_exclusive,
                    config.timeout_seconds,
                    config.chunk_hours,
                )
            else:
                raise
    df = build_dataframe(records)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"PSE_gen-jw_{timestamp}.csv"
    df.to_csv(out_path, index=False)
    return out_path


def main() -> int:
    if pd is None:
        print("Error: pandas is required. Please install pandas.", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(
        description="Export PSE 15-minute per-unit generation (gen-jw) data to CSV."
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
        help="Output directory for the CSV file (default: current directory).",
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
    parser.add_argument(
        "--chunk-hours",
        type=int,
        default=DEFAULT_CHUNK_HOURS,
        help=(
            "Split requests into time windows (hours) to avoid API pagination errors. "
            "Use 0 to disable chunking."
        ),
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
        chunk_hours=max(0, args.chunk_hours),
    )

    print(
        f"Pulling gen-jw data from {format_dt(config.start_dt)} UTC "
        f"to {format_dt(config.end_dt_exclusive)} UTC (exclusive)."
    )

    out_dir = Path(args.out_dir)
    out_path = run_export(config, out_dir)
    print(f"Export complete: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
