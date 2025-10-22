# C:\REPS\test_parquet_read.py
import pandas as pd
from pathlib import Path
p = Path(r"C:\REPS\data\output_data.parquet")
print("Checking:", p)
print("Exists?:", p.exists(), "Is file?:", p.is_file())
if p.exists() and p.is_file():
    df = pd.read_parquet(p)
    print("Read OK. shape:", df.shape)
    cols = list(df.columns)
    print("Columns (count):", len(cols))
    nit_like = [c for c in cols if 'nit' in c.lower()]
    print("Columns that look like NIT:", nit_like)
    for c in nit_like:
        sample = df[c].dropna().astype(str).unique()[:10].tolist()
        print(f"  - {c}: {len(df[c].dropna())} non-null, examples: {sample}")
    print("Head (first 3 rows):")
    print(df.head(3).to_dict(orient='records'))
else:
    print("File not present at that path.")