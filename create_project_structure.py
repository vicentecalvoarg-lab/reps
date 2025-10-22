"""Utility to create the folder structure under C:/REPS and example data folder.
Run this once on Windows to create directories:
    python create_project_structure.py

This script only creates directories. Place your data files (parquet / csv) as described in README.md.
"""
import os
from pathlib import Path

BASE = Path("C:/REPS")

dirs = [
    BASE,
    BASE / "data",
    BASE / "app",
    BASE / "app" / "components",
    BASE / "app" / "pages",
    BASE / "app" / "tests",
]

for d in dirs:
    d.mkdir(parents=True, exist_ok=True)
    print(f"Ensured directory: {d}")

print("\nDone. Now copy the files provided (the app/ tree) into C:/REPS or run Streamlit from the project root that contains the 'app' package.")
print("Put your data file at: C:/REPS/data/output_data.parquet (or output_data.csv). See README.md for details.")
