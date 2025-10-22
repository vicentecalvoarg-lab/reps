"""Helpers to display tables and Export to Excel."""
import io
import pandas as pd
import streamlit as st

def download_excel(dfs: dict, filename="report.xlsx"):
    """
    dfs: mapping sheet_name -> DataFrame
    returns a st.download_button
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        for sheet, df in dfs.items():
            try:
                df.to_excel(writer, sheet_name=sheet[:31], index=False)
            except Exception:
                # fallback: convert to string
                pd.DataFrame(df).to_excel(writer, sheet_name=sheet[:31], index=False)
    data = buf.getvalue()
    return st.download_button("⬇️ Descargar simulación (Excel)", data=data, file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
