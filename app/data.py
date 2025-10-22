"""Data loading and basic helpers (cached)."""
from pathlib import Path
import pandas as pd
import streamlit as st
import re
from app import config

@st.cache_data(show_spinner=False)
def load_data(path: str | None = None):
    """
    Load dataset. If path None, try DEFAULT_PARQUET then DEFAULT_CSV.
    Returns a DataFrame.
    """
    p = None
    if path:
        p = Path(path)
    else:
        if config.DEFAULT_PARQUET.exists():
            p = config.DEFAULT_PARQUET
        elif config.DEFAULT_CSV.exists():
            p = config.DEFAULT_CSV
    if p is None or not p.exists():
        raise FileNotFoundError(f"No data file found. Put your dataset at {config.DEFAULT_PARQUET} or {config.DEFAULT_CSV} or pass path to load_data().")
    if p.suffix.lower() in [".parquet"]:
        df = pd.read_parquet(p)
    else:
        df = pd.read_csv(p)
    # Normalize numeric capacity installed
    if 'num cantidad capacidad instalada' in df.columns:
        df['num cantidad capacidad instalada'] = pd.to_numeric(df['num cantidad capacidad instalada'], errors='coerce').fillna(0)
    # Some minimal date handling
    if 'Fecha Corte' in df.columns:
        df['Fecha Corte'] = pd.to_datetime(df['Fecha Corte'], errors='coerce')
    return df

def explode_nits_regex(df, nit_col='nit IPS', token_min_length=6):
    """
    Extract possible NIT tokens from a messy nit column.
    Returns DataFrame with columns: _orig_index, nit_token, nit_normalized
    """
    df = df.copy()
    df['_orig_index'] = df.index
    if nit_col not in df.columns:
        return pd.DataFrame(columns=['_orig_index', 'nit_token', 'nit_normalized'])
    tokens_rows = []
    pattern = re.compile(r'[\d\.,\-\s]{' + str(token_min_length) + r',}')
    for idx, val in df[nit_col].fillna('').astype(str).items():
        text = val.strip()
        if text == '':
            continue
        found = pattern.findall(text)
        if not found:
            if len(re.sub(r'\D', '', text)) >= 3:
                found = [text]
        for tok in found:
            tok_clean = tok.strip()
            nit_norm = re.sub(r'\D', '', tok_clean)
            if nit_norm == "":
                continue
            tokens_rows.append({'_orig_index': idx, 'nit_token': tok_clean, 'nit_normalized': nit_norm})
    if not tokens_rows:
        return pd.DataFrame(columns=['_orig_index', 'nit_token', 'nit_normalized'])
    return pd.DataFrame(tokens_rows)
