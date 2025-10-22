"""Configuration for the dashboard.

By default DATA_DIR is C:/REPS/data but can be overridden setting env var REPS_DATA_DIR.
"""
from pathlib import Path
import os

DATA_DIR = Path(os.environ.get("REPS_DATA_DIR", "C:/REPS/data"))
# default filename we expect
DEFAULT_PARQUET = DATA_DIR / "output_data.parquet"
DEFAULT_CSV = DATA_DIR / "output_data.csv"
