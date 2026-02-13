from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_CSV_PATH = Path(
    "/Users/pkiszk/Library/CloudStorage/OneDrive-Osobisty/009_PK/08 Learning/"
    "Curtailment_Excel/PSE_gen-jw_2025-01.csv"
)

EXCLUDED_PERCENTILE_CODE_PREFIXES = (
    "ZRN",
    "PZR",
    "JW7",
    "WLC",
    "ZGR",
    "SNA",
    "ZWA",
)


def is_excluded_from_percentiles(resource_code: str) -> bool:
    """Return True if resource_code belongs to an excluded percentile prefix."""
    code = str(resource_code)
    return any(code.startswith(prefix) for prefix in EXCLUDED_PERCENTILE_CODE_PREFIXES)


def get_percentile_base_codes(df: pd.DataFrame) -> list[str]:
    """Return sorted resource_code list eligible for percentile calculations."""
    if "resource_code" not in df.columns:
        raise ValueError("Missing required column: resource_code")
    all_codes = sorted(code for code in df["resource_code"].dropna().unique())
    return [code for code in all_codes if not is_excluded_from_percentiles(code)]


def load_pse_gen_jw_csv(csv_path: Path | str = DEFAULT_CSV_PATH) -> pd.DataFrame:
    """Load PSE_gen-jw CSV into a pandas DataFrame."""
    path = Path(csv_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    return pd.read_csv(path)


def min_positive_per_resource(df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per resource_code with the minimum positive wartosc."""
    required = {"resource_code", "wartosc"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    work = df.copy()
    work["wartosc"] = pd.to_numeric(work["wartosc"], errors="coerce")
    positive = work[work["wartosc"] > 0].copy()
    if positive.empty:
        return positive

    idx = positive.groupby("resource_code")["wartosc"].idxmin()
    result = positive.loc[idx].sort_values(["resource_code", "wartosc"])
    return result


def records_for_resource(df: pd.DataFrame, resource_code: str) -> pd.DataFrame:
    """Return all records for a given resource_code."""
    if "resource_code" not in df.columns:
        raise ValueError("Missing required column: resource_code")
    return df[df["resource_code"] == resource_code].copy()


def resource_wartosc_stats(df: pd.DataFrame, resource_code: str) -> tuple[float, float]:
    """Return (minimum positive wartosc, 5th percentile of non-zero wartosc)."""
    target = records_for_resource(df, resource_code).copy()
    if target.empty:
        raise ValueError(f"No records found for resource_code={resource_code!r}")

    wartosc = pd.to_numeric(target["wartosc"], errors="coerce").dropna()
    if wartosc.empty:
        raise ValueError(f"No numeric wartosc values for resource_code={resource_code!r}")

    positive = wartosc[wartosc > 0]
    if positive.empty:
        raise ValueError(
            f"No positive wartosc values for resource_code={resource_code!r}"
        )

    non_zero = wartosc[wartosc != 0]
    if non_zero.empty:
        raise ValueError(
            f"No non-zero wartosc values for resource_code={resource_code!r}"
        )

    min_non_zero = float(positive.min())
    percentile_5 = float(non_zero.quantile(0.05))
    return min_non_zero, percentile_5


def zero_streaks_hours(df: pd.DataFrame, resource_code: str) -> pd.DataFrame:
    """
    Return consecutive zero-value streaks and their lengths in hours.

    Output columns:
    - streak_id
    - start_ts
    - end_ts
    - intervals
    - hours
    """
    target = records_for_resource(df, resource_code).copy()
    if target.empty:
        raise ValueError(f"No records found for resource_code={resource_code!r}")

    ts_col = "dtime_utc" if "dtime_utc" in target.columns else "dtime"
    if ts_col not in target.columns:
        raise ValueError("Missing timestamp column: expected dtime_utc or dtime")

    target["timestamp"] = pd.to_datetime(target[ts_col], errors="coerce")
    target["wartosc"] = pd.to_numeric(target["wartosc"], errors="coerce")
    target = target.dropna(subset=["timestamp", "wartosc"]).sort_values("timestamp")
    if target.empty:
        raise ValueError(f"No valid timestamp/wartosc rows for {resource_code!r}")

    diffs = target["timestamp"].diff().dt.total_seconds().div(3600)
    diffs = diffs[diffs > 0]
    step_hours = float(diffs.mode().iloc[0]) if not diffs.empty else 0.25
    tolerance = max(1e-9, step_hours * 0.01)

    is_zero = target["wartosc"] == 0
    gap_break = diffs.reindex(target.index).fillna(step_hours).sub(step_hours).abs() > tolerance
    starts = is_zero & ((~is_zero.shift(fill_value=False)) | gap_break)
    streak_id = starts.cumsum()

    zero_rows = target[is_zero].copy()
    if zero_rows.empty:
        return pd.DataFrame(columns=["streak_id", "start_ts", "end_ts", "intervals", "hours"])

    zero_rows["streak_id"] = streak_id[is_zero]
    streaks = (
        zero_rows.groupby("streak_id")
        .agg(
            start_ts=("timestamp", "min"),
            end_ts=("timestamp", "max"),
            intervals=("timestamp", "size"),
        )
        .reset_index()
    )
    streaks["hours"] = streaks["intervals"] * step_hours
    return streaks


def bel_codes_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return stats for all resource_code values starting with 'BEL'.

    Columns:
    - resource_code
    - min_non_zero_wartosc
    - p5_non_zero_wartosc
    - zero_streak_count
    - longest_zero_streak_h
    - zero_streak_hours
    """
    if "resource_code" not in df.columns:
        raise ValueError("Missing required column: resource_code")

    bel_codes = sorted(
        code for code in df["resource_code"].dropna().unique() if str(code).startswith("BEL")
    )

    rows = []
    for code in bel_codes:
        min_non_zero, p5_non_zero = resource_wartosc_stats(df, code)
        streaks = zero_streaks_hours(df, code)
        streak_hours = streaks["hours"].round(2).tolist() if not streaks.empty else []
        rows.append(
            {
                "resource_code": code,
                "min_non_zero_wartosc": min_non_zero,
                "p5_non_zero_wartosc": p5_non_zero,
                "zero_streak_count": int(len(streaks)),
                "longest_zero_streak_h": float(streaks["hours"].max()) if not streaks.empty else 0.0,
                "zero_streak_hours": streak_hours,
            }
        )

    return pd.DataFrame(rows).sort_values("resource_code").reset_index(drop=True)


def all_codes_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return stats for all unique resource_code values.

    Columns:
    - resource_code
    - percentile_base_included
    - min_non_zero_wartosc
    - p1_non_zero_wartosc
    - p2_non_zero_wartosc
    - p3_non_zero_wartosc
    - p5_non_zero_wartosc
    - zero_streak_count
    - longest_zero_streak_h
    - zero_streak_hours
    """
    if "resource_code" not in df.columns:
        raise ValueError("Missing required column: resource_code")

    codes = sorted(code for code in df["resource_code"].dropna().unique())
    percentile_base_codes = set(get_percentile_base_codes(df))
    rows = []
    for code in codes:
        subset = records_for_resource(df, code)
        wartosc = pd.to_numeric(subset["wartosc"], errors="coerce").dropna()
        positive = wartosc[wartosc > 0]
        non_zero = wartosc[wartosc != 0]
        percentile_base_included = code in percentile_base_codes

        streaks = zero_streaks_hours(df, code)
        streak_hours = streaks["hours"].round(2).tolist() if not streaks.empty else []

        rows.append(
            {
                "resource_code": code,
                "percentile_base_included": percentile_base_included,
                "min_non_zero_wartosc": (
                    float(positive.min()) if not positive.empty else np.nan
                ),
                "p1_non_zero_wartosc": (
                    float(non_zero.quantile(0.01))
                    if percentile_base_included and not non_zero.empty
                    else np.nan
                ),
                "p2_non_zero_wartosc": (
                    float(non_zero.quantile(0.02))
                    if percentile_base_included and not non_zero.empty
                    else np.nan
                ),
                "p3_non_zero_wartosc": (
                    float(non_zero.quantile(0.03))
                    if percentile_base_included and not non_zero.empty
                    else np.nan
                ),
                "p5_non_zero_wartosc": (
                    float(non_zero.quantile(0.05))
                    if percentile_base_included and not non_zero.empty
                    else np.nan
                ),
                "zero_streak_count": int(len(streaks)),
                "longest_zero_streak_h": (
                    float(streaks["hours"].max()) if not streaks.empty else 0.0
                ),
                "zero_streak_hours": streak_hours,
            }
        )

    return pd.DataFrame(rows).sort_values("resource_code").reset_index(drop=True)


def p5_subtotals_by_family(stats_df: pd.DataFrame) -> pd.DataFrame:
    """
    Group p5_non_zero_wartosc subtotals by resource_code family prefix.

    Example: BEL 2-02, BEL 2-03 -> family BEL subtotal.
    """
    required = {
        "resource_code",
        "p1_non_zero_wartosc",
        "p2_non_zero_wartosc",
        "p3_non_zero_wartosc",
        "p5_non_zero_wartosc",
    }
    missing = required - set(stats_df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    work = stats_df.copy()
    if "percentile_base_included" not in work.columns:
        work["percentile_base_included"] = ~work["resource_code"].apply(
            is_excluded_from_percentiles
        )

    work["code_family"] = (
        work["resource_code"]
        .astype(str)
        .str.extract(r"^([A-Za-z]+)", expand=False)
        .fillna("UNKNOWN")
    )

    subtotals = (
        work.groupby("code_family", as_index=False)
        .agg(
            resource_code_count=("resource_code", "size"),
            percentile_base_code_count=("percentile_base_included", "sum"),
            p1_non_zero_wartosc_subtotal=("p1_non_zero_wartosc", "sum"),
            p2_non_zero_wartosc_subtotal=("p2_non_zero_wartosc", "sum"),
            p3_non_zero_wartosc_subtotal=("p3_non_zero_wartosc", "sum"),
            p5_non_zero_wartosc_subtotal=("p5_non_zero_wartosc", "sum"),
        )
        .sort_values("code_family")
        .reset_index(drop=True)
    )
    return subtotals


if __name__ == "__main__":
    df = load_pse_gen_jw_csv()
    print(f"Loaded {len(df)} rows x {len(df.columns)} columns from: {DEFAULT_CSV_PATH}")
    print("\nHeaders:")
    print(df.columns.tolist())
    print("\nFirst rows:")
    print(df.head())

    minima = min_positive_per_resource(df)
    print("\nMinimum positive wartosc per resource_code:")
    if minima.empty:
        print("No positive values found.")
    else:
        cols = [c for c in ["resource_code", "wartosc", "dtime", "period", "power_plant"] if c in minima.columns]
        print(minima[cols].to_string(index=False))

    target_resource = "BEL 2-02"
    target_df = records_for_resource(df, target_resource)
    print(f"\nAll records for {target_resource}: {len(target_df)} rows")
    if target_df.empty:
        print("No matching records found.")
    else:
        print(target_df.to_string(index=False))

    min_non_zero, percentile_5 = resource_wartosc_stats(df, target_resource)
    print(f"\n{target_resource} minimum non-zero wartosc: {min_non_zero:.4f}")
    print(
        f"{target_resource} wartosc 5th percentile (bottom, excluding zeros): "
        f"{percentile_5:.4f}"
    )

    streaks = zero_streaks_hours(df, target_resource)
    print(f"\n{target_resource} zero-value streaks: {len(streaks)}")
    if streaks.empty:
        print("No zero-value streaks found.")
    else:
        print(streaks.to_string(index=False))
        print(f"\nLongest zero streak (hours): {streaks['hours'].max():.2f}")

    bel_stats = bel_codes_stats(df)
    print("\nAll BEL codes stats:")
    if bel_stats.empty:
        print("No BEL resource_code values found.")
    else:
        print(bel_stats.to_string(index=False))
        p5_total = float(bel_stats["p5_non_zero_wartosc"].sum())
        print(f"\nTotal p5_non_zero_wartosc across BEL codes: {p5_total:.4f}")

    all_stats = all_codes_stats(df)
    print("\nAll resource_code stats:")
    if all_stats.empty:
        print("No resource_code values found.")
    else:
        print(all_stats.to_string(index=False))
        base_count = int(all_stats["percentile_base_included"].sum())
        print(
            f"\nPercentile base codes: {base_count}/{len(all_stats)} "
            f"(excluded prefixes: {list(EXCLUDED_PERCENTILE_CODE_PREFIXES)})"
        )
        grand_total_p1 = float(all_stats["p1_non_zero_wartosc"].sum(skipna=True))
        grand_total_p2 = float(all_stats["p2_non_zero_wartosc"].sum(skipna=True))
        grand_total_p3 = float(all_stats["p3_non_zero_wartosc"].sum(skipna=True))
        grand_total = float(all_stats["p5_non_zero_wartosc"].sum(skipna=True))
        print(f"\nGrand total p1_non_zero_wartosc across all codes: {grand_total_p1:.4f}")
        print(f"\nGrand total p2_non_zero_wartosc across all codes: {grand_total_p2:.4f}")
        print(f"\nGrand total p3_non_zero_wartosc across all codes: {grand_total_p3:.4f}")
        print(f"\nGrand total p5_non_zero_wartosc across all codes: {grand_total:.4f}")

        family_subtotals = p5_subtotals_by_family(all_stats)
        print("\nSubtotals by code family:")
        print(family_subtotals.to_string(index=False))
