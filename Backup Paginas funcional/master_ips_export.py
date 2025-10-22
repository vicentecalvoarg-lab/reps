"""
master_ips_export.py

Utility to export the dashboard's ctx['outputs'] to a single Excel workbook (.xlsx)
with one sheet per DataFrame plus a METADATA sheet. Provides a UI helper to show
a download button in Streamlit.

Usage:
 - Save this file as app/pagina/master_ips_export.py
 - From your main dashboard runner (after blocks have populated ctx['outputs']),
   import and call:
       from app.pagina import master_ips_export
       master_ips_export.show_export_button(ctx)

Requirements:
 - pandas
 - openpyxl (optional, used to apply number formats in the workbook)
"""
from typing import Dict, Any
import io
import datetime
import pandas as pd
import streamlit as st

try:
    import openpyxl
    from openpyxl.utils import get_column_letter
except Exception:
    openpyxl = None  # formatting will be skipped if openpyxl is not installed


def _apply_number_format_to_worksheet(ws, df: pd.DataFrame):
    """
    Apply a number format with thousands separators to numeric columns already
    written to the worksheet. This modifies cells in-place using openpyxl.
    """
    if openpyxl is None or df is None or df.empty:
        return
    nrows = df.shape[0]
    ncols = df.shape[1]
    if nrows == 0 or ncols == 0:
        return
    for j, col in enumerate(df.columns, start=1):
        try:
            is_num = pd.api.types.is_numeric_dtype(df[col])
        except Exception:
            is_num = False
        if not is_num:
            continue
        sample = df[col].dropna().head(10)
        has_decimal = False
        try:
            has_decimal = any(float(x) % 1 != 0 for x in sample.astype(float)) if not sample.empty else False
        except Exception:
            has_decimal = False
        fmt = '#,##0.00' if has_decimal else '#,##0'
        col_letter = get_column_letter(j)
        for i in range(2, 2 + nrows):
            cell = ws[f'{col_letter}{i}']
            try:
                if isinstance(cell.value, (int, float)):
                    cell.number_format = fmt
            except Exception:
                continue


def _safe_sheet_name(name: str) -> str:
    """
    Make a safe Excel sheet name (<=31 chars, remove invalid characters).
    """
    s = str(name)[:31]
    for ch in [':', '\\', '/', '?', '*', '[', ']']:
        s = s.replace(ch, '_')
    return s


def build_excel_bytes_from_ctx(ctx: Dict[str, Any]) -> bytes:
    """
    Build an in-memory .xlsx file containing:
     - METADATA sheet (filters, timestamp, available outputs)
     - One sheet per DataFrame in ctx['outputs'] (sheet named by key)
     - Optional preview sheet for df_result (first 200 rows)
    Returns bytes of the generated Excel file.
    """
    outputs = ctx.get('outputs', {}) or {}
    buf = io.BytesIO()
    timestamp = datetime.datetime.now().isoformat(timespec='seconds')

    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        # METADATA sheet
        metadata = {
            'generated_at': timestamp,
            'filters': str(ctx.get('filters', {})),
            'giro_path': str(ctx.get('giro_path', '')),
            'giro_date_range': str(ctx.get('giro_date_range', '')),
            'available_outputs': ", ".join(list(outputs.keys()))
        }
        md_df = pd.DataFrame(list(metadata.items()), columns=['key', 'value'])
        md_df.to_excel(writer, sheet_name=_safe_sheet_name('METADATA'), index=False)

        # Write each output DataFrame to a separate sheet
        for key, val in outputs.items():
            sheet_name = _safe_sheet_name(str(key))
            try:
                if isinstance(val, pd.DataFrame):
                    df = val.copy()
                    df.columns = [str(c) for c in df.columns]
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                else:
                    pd.DataFrame({str(key): [str(val)]}).to_excel(writer, sheet_name=sheet_name, index=False)
            except Exception as e:
                pd.DataFrame({'error': [str(e)]}).to_excel(writer, sheet_name=sheet_name, index=False)

        # Add a preview of df_result if present
        try:
            df_result = ctx.get('df_result')
            if isinstance(df_result, pd.DataFrame) and not df_result.empty:
                preview = df_result.head(200).copy()
                preview.to_excel(writer, sheet_name=_safe_sheet_name('DF_RESULT_preview'), index=False)
        except Exception:
            pass

        # Finalize writer and then, if openpyxl available, post-process formatting
        writer.save()

        if openpyxl is not None:
            try:
                wb = writer.book
                for key, val in outputs.items():
                    sheet_name = _safe_sheet_name(str(key))
                    if sheet_name in wb.sheetnames and isinstance(val, pd.DataFrame) and not val.empty:
                        ws = wb[sheet_name]
                        _apply_number_format_to_worksheet(ws, val)
                if 'DF_RESULT_preview' in wb.sheetnames and isinstance(df_result, pd.DataFrame):
                    _apply_number_format_to_worksheet(wb['DF_RESULT_preview'], df_result.head(200))
                buf.seek(0)
                wb.save(buf)
            except Exception:
                # if formatting fails, ignore and return unformatted bytes
                pass

    buf.seek(0)
    return buf.read()


def show_export_button(ctx: Dict[str, Any], button_label: str = "Exportar todo a Excel (.xlsx)"):
    """
    Streamlit UI helper. When the button is clicked the workbook is generated
    and a download button is shown to download the workbook.
    """
    st.markdown("### Exportar contenidos")
    if st.button(button_label):
        with st.spinner("Generando archivo Excel..."):
            try:
                xbytes = build_excel_bytes_from_ctx(ctx)
                now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"master_ips_export_{now}.xlsx"
                st.download_button("Descargar Excel", data=xbytes, file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            except Exception as e:
                st.error(f"No fue posible generar el Excel: {e}")