"""
enrich_vehicles_with_make_gui.py

This file is now GUI-only.

Responsibilities
----------------
1. Let the user choose an input CSV file.
2. Automatically build the output CSV path in the same folder.
3. Call processor.enrich_csv_with_vehicle_data(...)
4. Show success or error messages.

All validation, lookup, and CSV processing logic now lives in:
- validation.py
- lookup.py
- processor.py
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox

from dotenv import load_dotenv

from processor import enrich_csv_with_vehicle_data
from lookup import VDG_API_KEY


# Load variables from .env
load_dotenv()


def launch_gui() -> None:
    """
    Launch the Tkinter GUI.
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
        """Run enrichment using the selected input file."""
        input_path = input_var.get().strip()

        if not input_path:
            messagebox.showerror("Error", "Please select an input CSV file.")
            return

        # Build output path in the same directory as input
        input_dir, input_filename = os.path.split(input_path)
        name, ext = os.path.splitext(input_filename)
        if not ext:
            ext = ".csv"

        output_filename = f"{name}_output{ext}"
        output_path = os.path.join(input_dir, output_filename)

        try:
            run_button.config(state="disabled")
            root.update_idletasks()

            enrich_csv_with_vehicle_data(
                input_path=input_path,
                output_path=output_path,
                sleep_seconds=0.2,
            )

            messagebox.showinfo(
                "Success",
                f"Enriched CSV has been saved as:\n{output_path}",
            )

        except Exception as e:
            messagebox.showerror("Error", f"Something went wrong:\n{e}")

        finally:
            run_button.config(state="normal")

    # Build window
    root = tk.Tk()
    root.title("Vehicle Data Enricher")
    root.configure(padx=10, pady=10)

    input_var = tk.StringVar()

    tk.Label(root, text="Input CSV:").grid(row=0, column=0, sticky="w")
    tk.Entry(root, textvariable=input_var, width=50).grid(row=0, column=1, padx=5)
    tk.Button(root, text="Browse…", command=choose_input).grid(row=0, column=2)

    run_button = tk.Button(root, text="Run enrichment", command=run_enrichment)
    run_button.grid(row=1, column=0, columnspan=3, pady=(10, 0))

    root.grid_columnconfigure(1, weight=1)

    root.mainloop()


if __name__ == "__main__":
    if not VDG_API_KEY:
        raise RuntimeError(
            "VDG_API_KEY was not found.\n"
            "Create a .env file in the same folder as the script and add:\n"
            "VDG_API_KEY=your-real-api-key-here"
        )

    launch_gui()