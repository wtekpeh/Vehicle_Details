"""
processor.py

This module is responsible for:
1. Reading the CSV file.
2. Cleaning and validating registration numbers.
3. Calling the lookup module for valid registrations only.
4. Building enriched output columns.
5. Writing the result to a new CSV.

Why this module exists
----------------------
This keeps the main GUI file simple and keeps the CSV-processing logic
separate from both validation and API lookup code.
"""

import time
from typing import Dict, List, Optional

import pandas as pd

from validation import validate_registration
from lookup import lookup_vehicle_data, LookupResult


# =======================
# CONFIG / CONSTANTS
# =======================

REG_COLUMN_NAME = "License Plate"
MAKE_COLUMN_NAME = "Make"
TYPE_APPROVAL_COLUMN_NAME = "Type Approval"

# New diagnostic / audit columns
CLEANED_REG_COLUMN_NAME = "Cleaned License Plate"
VALIDATION_REASON_COLUMN_NAME = "Validation Reason"
LOOKUP_STATUS_COLUMN_NAME = "Lookup Status"
LOOKUP_STATUS_CODE_COLUMN_NAME = "Lookup Status Code"


def enrich_csv_with_vehicle_data(
    input_path: str,
    output_path: str,
    sleep_seconds: float = 0.2,
) -> None:
    """
    Read the input CSV, validate registrations, look up vehicle data,
    and write the enriched result to a new CSV.

    Parameters
    ----------
    input_path : str
        Path to the source CSV file.
    output_path : str
        Path to save the enriched CSV file.
    sleep_seconds : float
        Delay between API calls. Helps respect the provider's rate limits.
    """

    print(f"[INFO] Reading CSV from: {input_path}")
    df = pd.read_csv(input_path)

    # 1. Ensure expected column exists
    if REG_COLUMN_NAME not in df.columns:
        raise KeyError(
            f"Expected a column named '{REG_COLUMN_NAME}' in the CSV, "
            f"but found: {list(df.columns)}"
        )

    # 2. Prepare output lists
    cleaned_regs: List[Optional[str]] = []
    validation_reasons: List[str] = []
    makes: List[Optional[str]] = []
    type_approvals: List[Optional[str]] = []
    lookup_statuses: List[str] = []
    lookup_status_codes: List[str] = []

    # 3. Cache lookup results so duplicate registrations do not consume extra paid lookups
    cache: Dict[str, LookupResult] = {}

    total_rows = len(df)
    print(f"[INFO] Starting processing for {total_rows} rows...")

    for idx, raw_reg in enumerate(df[REG_COLUMN_NAME]):
        if idx % 10 == 0:
            print(f"  - Processing row {idx + 1}/{total_rows} (raw='{raw_reg}')")

        # Step A: validate first
        validation = validate_registration(raw_reg)
        cleaned_reg = validation["cleaned"]
        is_valid = validation["is_valid"]
        validation_reason = validation["reason"]

        cleaned_regs.append(cleaned_reg or None)
        validation_reasons.append(validation_reason)

        # Step B: if invalid, skip API lookup
        if not is_valid:
            makes.append(None)
            type_approvals.append(None)
            lookup_statuses.append("Skipped before API")
            lookup_status_codes.append("PRE_VALIDATION_FAILED")
            continue

        # Step C: valid registration -> call API lookup
        lookup_result = lookup_vehicle_data(cleaned_reg, cache)

        if lookup_result["success"]:
            vehicle_data = lookup_result["vehicle_data"]
            makes.append(vehicle_data.get("make") or None)
            type_approvals.append(vehicle_data.get("typeApproval") or None)
            lookup_statuses.append(lookup_result["status_message"])
            lookup_status_codes.append(lookup_result["status_code"])
        else:
            makes.append(None)
            type_approvals.append(None)
            lookup_statuses.append(lookup_result["status_message"])
            lookup_status_codes.append(lookup_result["status_code"])

            print(
                f"[WARN] Lookup failed for '{cleaned_reg}' | "
                f"StatusCode={lookup_result['status_code']} | "
                f"Message={lookup_result['status_message']}"
            )

        # Step D: only delay when we actually called the API
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    # 4. Add output columns to DataFrame
    df[CLEANED_REG_COLUMN_NAME] = cleaned_regs
    df[VALIDATION_REASON_COLUMN_NAME] = validation_reasons
    df[MAKE_COLUMN_NAME] = makes
    df[TYPE_APPROVAL_COLUMN_NAME] = type_approvals
    df[LOOKUP_STATUS_COLUMN_NAME] = lookup_statuses
    df[LOOKUP_STATUS_CODE_COLUMN_NAME] = lookup_status_codes

    # 5. Write output CSV
    print(f"[INFO] Writing enriched CSV to: {output_path}")
    df.to_csv(output_path, index=False)
    print("[INFO] Done.")