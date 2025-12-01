"""
enrich_vehicles_with_make_gui.py

What this script does
---------------------
1. Lets you choose an input CSV file via a GUI (Tkinter file dialog).
2. Reads the CSV, which must contain a "License Plate" column.
3. For each registration:
   - Looks up vehicle data (currently TEST_MODE with dummy values).
   - Collects both:
       * make
       * typeApproval
4. Writes a new CSV in the SAME FOLDER as the input file with:
     <original_name>_output.csv
   and adds 2 new columns:
     - "Make"
     - "Type Approval"

Later, when you have DVLA API access:
- We will plug the real API call into `lookup_vehicle_data`.
- Set TEST_MODE = False.
"""

import os
import time
from typing import Dict, Optional, List, TypedDict

import pandas as pd
import requests  # used later for the real DVLA call

# --- Tkinter for GUI ---
import tkinter as tk
from tkinter import filedialog, messagebox


# =======================
# CONFIG / CONSTANTS
# =======================

# Column name in your CSV that holds the registration number.
# Change this if your header text is slightly different.
REG_COLUMN_NAME = "License Plate"

# NEW columns we will add to the CSV
MAKE_COLUMN_NAME = "Make"
TYPE_APPROVAL_COLUMN_NAME = "Type Approval"

# Environment variables for the real API (for later)
DVLA_API_KEY = os.getenv("DVLA_API_KEY")
DVLA_API_URL = os.getenv("DVLA_API_URL")

# Currently we are not calling the real API.
# When DVLA access is ready, change this to False and implement the real call.
TEST_MODE = True


class VehicleData(TypedDict, total=False):
    """
    Simple structure to hold the fields we care about from the API.
    You can extend this later if you want more fields (colour, fuelType, etc.).
    """
    make: str
    typeApproval: str


# =======================
# CORE LOOKUP FUNCTION
# =======================

def lookup_vehicle_data(reg: str, cache: Dict[str, VehicleData]) -> Optional[VehicleData]:
    """
    Given a registration number (e.g. "ML12FDA"), return vehicle data.

    Parameters
    ----------
    reg : str
        Cleaned registration number (upper-case, no spaces).
    cache : dict
        Used to store previously-seen reg → data, so we don't
        call the API twice for the same registration.

    Returns
    -------
    Optional[VehicleData]
        A dict like:
           {
             "make": "ROVER",
             "typeApproval": "N1"
           }
        or None if not found / error.

    Current behaviour
    -----------------
    - In TEST_MODE, we do NOT call any external service. We just return
      dummy values so you can test the pipeline.
    - When TEST_MODE=False, this function will call the real DVLA API
      based on their docs and your API key.
    """

    # 1. First, check the cache
    if reg in cache:
        return cache[reg]

    # 2. TEST MODE: no real HTTP call, just predictable fake values
    if TEST_MODE:
        dummy_data: VehicleData = {
            "make": f"MAKE_FOR_{reg}",
            "typeApproval": "TEST_TYPE",  # e.g. stands in for "N1"
        }
        cache[reg] = dummy_data
        return dummy_data

    # 3. REAL API CALL (for later)
    # ----------------------------
    if not DVLA_API_KEY or not DVLA_API_URL:
        raise RuntimeError(
            "DVLA_API_KEY or DVLA_API_URL is not set. "
            "Define them as environment variables before running."
        )

    try:
        # Example payload based on sample response you shared.
        # Exact details will come from DVLA docs.
        payload = {"registrationNumber": reg}
        headers = {
            "x-api-key": DVLA_API_KEY,
            "Content-Type": "application/json",
        }

        # Adjust POST/GET according to their docs
        response = requests.post(DVLA_API_URL, json=payload, headers=headers, timeout=10)
        response.raise_for_status()  # raises HTTPError for 4xx/5xx

        data = response.json()

        # Example expected JSON structure:
        # {
        #   "make": "ROVER",
        #   "typeApproval": "N1",
        #   ...
        # }
        vehicle_data: VehicleData = {
            "make": data.get("make", ""),
            "typeApproval": data.get("typeApproval", ""),
        }

        # Cache only if we got at least something useful
        if vehicle_data.get("make") or vehicle_data.get("typeApproval"):
            cache[reg] = vehicle_data

        return vehicle_data

    except Exception as e:
        # For now, just log to console and return None
        print(f"[WARN] Failed to look up reg '{reg}': {e}")
        return None


# =======================
# CSV ENRICHMENT LOGIC
# =======================

def enrich_csv_with_vehicle_data(
    input_path: str,
    output_path: str,
    sleep_seconds: float = 0.2,
) -> None:
    """
    Read `input_path` CSV, look up vehicle data for each registration,
    and write a new CSV with added columns 'Make' and 'Type Approval'.

    Parameters
    ----------
    input_path : str
        Path to the input CSV file.
    output_path : str
        Path to the output CSV file (auto-generated in same folder as input).
    sleep_seconds : float
        Delay between API calls to respect rate limits.
        (In TEST_MODE you can safely set this to 0 if you want.)
    """

    print(f"[INFO] Reading CSV from: {input_path}")
    df = pd.read_csv(input_path)

    # Ensure the expected column exists
    if REG_COLUMN_NAME not in df.columns:
        raise KeyError(
            f"Expected a column named '{REG_COLUMN_NAME}' in the CSV, "
            f"but found: {list(df.columns)}"
        )

    # Clean registration numbers: string, trimmed, upper-case
    df[REG_COLUMN_NAME] = (
        df[REG_COLUMN_NAME]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    cache: Dict[str, VehicleData] = {}
    vehicle_data_list: List[Optional[VehicleData]] = []

    total_rows = len(df)
    print(f"[INFO] Starting lookup for {total_rows} rows… (TEST_MODE={TEST_MODE})")

    for idx, reg in enumerate(df[REG_COLUMN_NAME]):
        if idx % 10 == 0:
            print(f"  - Row {idx + 1}/{total_rows} (reg='{reg}')")

        # Handle empty / NaN
        if not reg or reg.lower() == "nan":
            vehicle_data_list.append(None)
            continue

        vd = lookup_vehicle_data(reg, cache)
        vehicle_data_list.append(vd)

        # Only sleep when talking to real API
        if sleep_seconds > 0 and not TEST_MODE:
            time.sleep(sleep_seconds)

    # Extract Make and Type Approval from the vehicle_data_list into columns
    makes: List[Optional[str]] = []
    type_approvals: List[Optional[str]] = []

    for vd in vehicle_data_list:
        if vd is None:
            makes.append(None)
            type_approvals.append(None)
        else:
            makes.append(vd.get("make") or None)
            type_approvals.append(vd.get("typeApproval") or None)

    # Add new columns to the DataFrame
    df[MAKE_COLUMN_NAME] = makes
    df[TYPE_APPROVAL_COLUMN_NAME] = type_approvals

    print(f"[INFO] Writing enriched CSV to: {output_path}")
    df.to_csv(output_path, index=False)
    print("[INFO] Done.")


# =======================
# TKINTER GUI
# =======================

def launch_gui() -> None:
    """
    Launch a simple Tkinter GUI that lets the user:
      - Browse for input CSV.
      - Automatically writes output CSV in the SAME folder as input,
        named <original_name>_output.csv.
    """

    def choose_input():
        """Open a file dialog to select the input CSV."""
        path = filedialog.askopenfilename(
            title="Select input CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            input_var.set(path)

    def run_enrichment():
        """Run the CSV enrichment using the selected input path."""
        input_path = input_var.get().strip()

        if not input_path:
            messagebox.showerror("Error", "Please select an input CSV file.")
            return

        # Build output path in the SAME directory as the input.
        # Example:
        #   input:  C:/data/vehicles.csv
        #   output: C:/data/vehicles_output.csv
        input_dir, input_filename = os.path.split(input_path)
        name, ext = os.path.splitext(input_filename)
        if not ext:
            ext = ".csv"
        output_filename = f"{name}_output{ext}"
        output_path = os.path.join(input_dir, output_filename)

        try:
            run_button.config(state="disabled")  # prevent double-clicks
            root.update_idletasks()

            # For now we can set sleep_seconds=0.0 (faster in TEST_MODE)
            enrich_csv_with_vehicle_data(
                input_path=input_path,
                output_path=output_path,
                sleep_seconds=0.0,
            )

            messagebox.showinfo(
                "Success",
                f"Enriched CSV has been saved as:\n{output_path}",
            )
        except Exception as e:
            messagebox.showerror("Error", f"Something went wrong:\n{e}")
        finally:
            run_button.config(state="normal")

    # --- Build the window ---

    root = tk.Tk()
    root.title("Vehicle Data Enricher")

    root.configure(padx=10, pady=10)

    # Tkinter variable to hold the input path
    input_var = tk.StringVar()

    # Row 0: Input file
    tk.Label(root, text="Input CSV:").grid(row=0, column=0, sticky="w")
    tk.Entry(root, textvariable=input_var, width=50).grid(row=0, column=1, padx=5)
    tk.Button(root, text="Browse…", command=choose_input).grid(row=0, column=2)

    # Row 1: Run button (no output picker anymore)
    run_button = tk.Button(root, text="Run enrichment", command=run_enrichment)
    run_button.grid(row=1, column=0, columnspan=3, pady=(10, 0))

    root.grid_columnconfigure(1, weight=1)

    root.mainloop()


# =======================
# ENTRY POINT
# =======================

if __name__ == "__main__":
    launch_gui()
