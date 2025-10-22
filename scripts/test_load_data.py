"""
Comprueba que load_data() funciona y cuánto tarda en leer el fichero principal.
Ejecuta:
    python C:\REPS\scripts\test_load_data.py
Salida:
- imprime la forma del DataFrame, primeras columnas y tiempo de carga.
"""
import time
from pathlib import Path
import traceback
import sys

# Asegura path del proyecto en sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from app.data import load_data
except Exception:
    print("No se pudo importar load_data() desde app.data.")
    traceback.print_exc()
    raise SystemExit(1)

print("Intentando cargar datos con app.data.load_data() ...")
t0 = time.time()
try:
    df = load_data()
    t1 = time.time()
    print(f"Carga OK (tiempo {t1-t0:.2f} s). Filas: {len(df):,}, Columnas: {len(df.columns)}")
    print("Primeras 10 columnas:", list(df.columns[:10]))
    print("Tipo de algunas columnas (primeras 10):")
    for c in df.columns[:10]:
        print(f" - {c!r}: {df[c].dtype}")
    print("\nMuestra 5 filas (primeras columnas):")
    print(df.head(5).to_string(index=False))
except Exception:
    t1 = time.time()
    print(f"Error tras {t1-t0:.2f} s cargando datos:")
    traceback.print_exc()
    raise SystemExit(1)