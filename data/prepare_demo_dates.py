#!/usr/bin/env python3
"""Prepare demo-ready CSV dates per drum.

This script scans CSV files in a directory and updates files that contain both
`drum_id` and `date` columns.

For each drum group in each file:
- 75% of records are assigned dates in the past (ending yesterday)
- 25% of records are assigned dates in the future (starting tomorrow)

Reference date defaults to 2026-04-22, matching the demo scenario.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Shift CSV dates for demo usage.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory containing CSV files (default: script directory).",
    )
    parser.add_argument(
        "--today",
        type=str,
        default="2026-04-22",
        help="Reference date in YYYY-MM-DD format (default: 2026-04-22).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files.",
    )
    return parser.parse_args()


def candidate_csvs(data_dir: Path) -> Iterable[Path]:
    for csv_path in sorted(data_dir.glob("*.csv")):
        if csv_path.name.startswith(".~lock"):
            continue
        yield csv_path


def build_new_dates(group_size: int, today: pd.Timestamp) -> pd.DatetimeIndex:
    if group_size <= 0:
        return pd.DatetimeIndex([])

    past_count = int(group_size * 0.75)
    future_count = group_size - past_count

    yesterday = today - pd.Timedelta(days=1)
    tomorrow = today + pd.Timedelta(days=1)

    past_dates = pd.DatetimeIndex([])
    if past_count > 0:
        start_past = yesterday - pd.Timedelta(days=past_count - 1)
        past_dates = pd.date_range(start=start_past, periods=past_count, freq="D")

    future_dates = pd.DatetimeIndex([])
    if future_count > 0:
        future_dates = pd.date_range(start=tomorrow, periods=future_count, freq="D")

    return past_dates.append(future_dates)


def _normalize_missing_decimal(value):
    """Fix values where decimal point appears to be missing.

    Examples:
    - 185015 -> 185.015
    - 96676  -> 96.676

    We only adjust unusually large values for cable-length fields.
    """
    if pd.isna(value):
        return value

    try:
        number = float(value)
    except (TypeError, ValueError):
        return value

    # Cable-length values in these demo files are expected in a few hundred meters.
    # If a value is very large, repeatedly shift by 1000 to restore decimal placement.
    while abs(number) >= 1000:
        number /= 1000.0

    return number


def process_file(csv_path: Path, today: pd.Timestamp, dry_run: bool) -> tuple[bool, str]:
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        return False, f"ERROR reading {csv_path.name}: {exc}"

    needed = {"drum_id", "date"}
    if not needed.issubset(df.columns):
        return False, f"SKIP {csv_path.name}: missing drum_id/date columns"

    try:
        df["date"] = pd.to_datetime(df["date"])
    except Exception as exc:
        return False, f"SKIP {csv_path.name}: invalid date column ({exc})"

    updated_df = df.copy()
    updated_count = 0

    for col in ("daily_min_cable_length_m", "daily_max_cable_length_m"):
        if col in updated_df.columns:
            updated_df[col] = updated_df[col].apply(_normalize_missing_decimal)

    for drum_id, idx in updated_df.groupby("drum_id").groups.items():
        drum_rows = updated_df.loc[idx].sort_values("date")
        new_dates = build_new_dates(len(drum_rows), today)

        updated_df.loc[drum_rows.index, "date"] = new_dates.values

        if "days_elapsed" in updated_df.columns:
            updated_df.loc[drum_rows.index, "days_elapsed"] = list(range(len(drum_rows)))

        updated_count += len(drum_rows)

    updated_df["date"] = pd.to_datetime(updated_df["date"]).dt.strftime("%Y-%m-%d")

    if not dry_run:
        updated_df.to_csv(csv_path, index=False)

    return True, f"OK {csv_path.name}: updated {updated_count} rows"


def main() -> None:
    args = parse_args()
    today = pd.to_datetime(args.today)

    if not args.data_dir.exists():
        raise SystemExit(f"Data directory does not exist: {args.data_dir}")

    print(f"Using data directory: {args.data_dir}")
    print(f"Reference date (today): {today.strftime('%Y-%m-%d')}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'WRITE'}")

    changed_files = 0
    scanned_files = 0

    for csv_path in candidate_csvs(args.data_dir):
        scanned_files += 1
        changed, message = process_file(csv_path, today, args.dry_run)
        print(message)
        if changed:
            changed_files += 1

    print("-")
    print(f"Scanned CSV files: {scanned_files}")
    print(f"Processed drum/date CSV files: {changed_files}")


if __name__ == "__main__":
    main()
