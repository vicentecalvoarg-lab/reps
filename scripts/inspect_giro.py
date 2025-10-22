"""
Inspección rápida del archivo C:/REPS/data/giro.parquet

Qué hace:
- Intenta leer el *schema* del parquet con pyarrow (no carga todo el dataset).
- Lee un bloque de muestra (primer row group o primeras filas) a pandas para obtener valores de ejemplo.
- Genera un informe CSV con, para cada columna:
    - nombre, tipo (schema), conteo no-nulo, conteo nulo, % nulo, cardinalidad (en la muestra),
      top-N valores (en la muestra) y estadísticas básicas para numéricos (min/max/mean/std).
- Guarda también un CSV con las primeras filas de muestra.
- Imprime por consola un resumen breve y la ruta de los archivos generados.

Salida:
- C:/REPS/data/giro_fields_report.csv
- C:/REPS/data/giro_sample_rows.csv
- C:/REPS/data/giro_schema.txt   (si pyarrow pudo leer el schema)

Cómo usar:
    1) Guarda este archivo como C:/REPS/scripts/inspect_giro.py
    2) Desde PowerShell / cmd ejecuta:
         python C:/REPS/scripts/inspect_giro.py
    3) Revisa los archivos generados en C:/REPS/data y pega aquí el giro_fields_report.csv o indícame
       cualquier columna de interés para que te diga cómo integrarla al dashboard.
"""
from pathlib import Path
import csv
import sys
import traceback

BASE = Path("C:/REPS")
DATA_DIR = BASE / "data"
PARQUET_PATH = DATA_DIR / "giro.parquet"

REPORT_CSV = DATA_DIR / "giro_fields_report.csv"
SAMPLE_CSV = DATA_DIR / "giro_sample_rows.csv"
SCHEMA_TXT = DATA_DIR / "giro_schema.txt"

TOP_N = 10            # top N values to capture per column in the sample
SAMPLE_ROW_LIMIT = 1000  # máximo filas a leer para el muestreo (si no es por row-group)

def main():
    if not PARQUET_PATH.exists():
        print(f"ERROR: no se encontró {PARQUET_PATH}")
        sys.exit(1)

    print("Inspeccionando:", PARQUET_PATH)
    # Try to use pyarrow to read schema and a small sample without loading whole file
    try:
        import pyarrow.parquet as pq
        import pyarrow as pa
        pqf = pq.ParquetFile(str(PARQUET_PATH))
        num_row_groups = pqf.num_row_groups
        num_rows = pqf.metadata.num_rows if pqf.metadata is not None else None
        schema = pqf.schema
        # write schema to file for quick inspection
        with open(SCHEMA_TXT, "w", encoding="utf-8") as f:
            f.write(str(schema))
        print(f"Schema guardado en {SCHEMA_TXT}")
        # choose a representative sample:
        if num_row_groups and num_row_groups > 0:
            # read first row group (fast)
            try:
                table = pqf.read_row_group(0)
                sample_df = table.to_pandas()
            except Exception:
                # fallback: read small table
                sample_table = pq.read_table(str(PARQUET_PATH), columns=None, use_threads=True)
                sample_df = sample_table.to_pandas().head(SAMPLE_ROW_LIMIT)
        else:
            # fallback: read small portion
            table = pq.read_table(str(PARQUET_PATH), columns=None)
            sample_df = table.to_pandas().head(SAMPLE_ROW_LIMIT)
    except Exception as e:
        # If pyarrow missing or fails, fallback to pandas (may load entire dataset)
        print("Aviso: fallo lectura con pyarrow (o no está instalado). Intentando con pandas.read_parquet ...")
        try:
            import pandas as pd
            df_full = pd.read_parquet(str(PARQUET_PATH))
            num_rows = len(df_full)
            sample_df = df_full.head(SAMPLE_ROW_LIMIT).copy()
            # write trivial schema
            with open(SCHEMA_TXT, "w", encoding="utf-8") as f:
                f.write("Schema obtenido vía pandas\n")
                f.write(str(df_full.dtypes))
            print(f"Schema guardado en {SCHEMA_TXT}")
        except Exception:
            print("Error leyendo el parquet con pandas. Detalle:")
            traceback.print_exc()
            sys.exit(1)

    # Ensure sample_df exists
    if 'sample_df' not in locals() or sample_df is None or sample_df.shape[0] == 0:
        print("No se pudo obtener muestra del archivo.")
        sys.exit(1)

    # Save sample rows for inspection
    try:
        sample_df.to_csv(SAMPLE_CSV, index=False)
        print(f"Muestra guardada en {SAMPLE_CSV} ({len(sample_df)} filas).")
    except Exception:
        print("No se pudo guardar sample CSV. Intentando guardar con CSV writer.")
        sample_df.head(50).to_csv(SAMPLE_CSV, index=False)
        print(f"Muestra guardada en {SAMPLE_CSV} (fallback).")

    # Build report per column using the sample (fast) and limited stats.
    import pandas as pd
    report_rows = []
    df_sample = sample_df
    # If full df loaded in pandas earlier, use it to compute exact counts for smaller datasets
    df_full = None
    try:
        import pandas as _pd
        if 'df_full' in locals():
            df_full = locals()['df_full']
    except Exception:
        df_full = None

    columns = list(df_sample.columns)
    for col in columns:
        dtype = str(df_sample[col].dtype)
        non_null = int(df_sample[col].notna().sum())
        nulls = int(df_sample[col].isna().sum())
        pct_null = round(100.0 * nulls / len(df_sample), 2) if len(df_sample) > 0 else None

        # If df_full available and not huge, compute real unique counts and nulls
        unique_count = None
        try:
            if df_full is not None and len(df_full) <= 2000000:  # avoid heavy ops
                unique_count = int(df_full[col].dropna().astype(str).nunique())
            else:
                unique_count = int(df_sample[col].dropna().astype(str).nunique())
        except Exception:
            unique_count = int(df_sample[col].dropna().astype(str).nunique())

        top_values = []
        try:
            vc = df_sample[col].astype(str).value_counts(dropna=True)
            top_values = [f"{v} ({int(cnt)})" for v, cnt in zip(vc.index[:TOP_N], vc.iloc[:TOP_N])]
        except Exception:
            top_values = []

        # numeric stats when applicable
        num_stats = {}
        if pd.api.types.is_numeric_dtype(df_sample[col]):
            try:
                ser = pd.to_numeric(df_sample[col], errors='coerce')
                num_stats = {
                    'min': float(ser.min()) if not ser.dropna().empty else None,
                    'max': float(ser.max()) if not ser.dropna().empty else None,
                    'mean': float(ser.mean()) if not ser.dropna().empty else None,
                    'std': float(ser.std()) if not ser.dropna().empty else None,
                }
            except Exception:
                num_stats = {}

        report_rows.append({
            'column': col,
            'dtype': dtype,
            'non_null_in_sample': non_null,
            'nulls_in_sample': nulls,
            'pct_null_in_sample': pct_null,
            'unique_count_estimate': unique_count,
            'top_values_sample': " | ".join(top_values),
            'numeric_min': num_stats.get('min', ''),
            'numeric_max': num_stats.get('max', ''),
            'numeric_mean': num_stats.get('mean', ''),
            'numeric_std': num_stats.get('std', ''),
        })

    # Write CSV report
    import csv
    keys = ['column','dtype','non_null_in_sample','nulls_in_sample','pct_null_in_sample','unique_count_estimate','top_values_sample','numeric_min','numeric_max','numeric_mean','numeric_std']
    try:
        with open(REPORT_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for r in report_rows:
                writer.writerow(r)
        print(f"Informe de campos guardado en: {REPORT_CSV}")
    except Exception:
        print("ERROR guardando informe CSV:")
        traceback.print_exc()
        sys.exit(1)

    # Print brief summary to console
    print("\nColumnas detectadas:")
    for r in report_rows:
        print(f" - {r['column']} (dtype={r['dtype']}) | nulls={r['nulls_in_sample']}/{len(df_sample)} | unique_est={r['unique_count_estimate']}")

    print("\nTop values (muestra) por algunas columnas (ver CSV para detalle):")
    for r in report_rows[:min(20, len(report_rows))]:
        print(f" * {r['column']}: {r['top_values_sample'][:200]}")

    print("\nHecho. Por favor revisa los archivos en C:/REPS/data:")
    print(" -", REPORT_CSV)
    print(" -", SAMPLE_CSV)
    print(" -", SCHEMA_TXT)
    print("\nSi quieres, pega aquí el contenido de giro_fields_report.csv (o algunas filas) y te indico los pasos siguientes para integrar 'giro' al dashboard.")
    return 0

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)