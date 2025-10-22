import importlib, traceback, sys

modules = [
    'app.pagina.analysis_ips',
    'app.pagina.giro_directo',
    'app.pagina.comparaciones'
]

for m in modules:
    print("---- Intentando importar:", m)
    try:
        importlib.import_module(m)
        print("IMPORT OK:", m, "\n")
    except Exception:
        print("IMPORT ERROR:", m)
        traceback.print_exc()
        print("\n")