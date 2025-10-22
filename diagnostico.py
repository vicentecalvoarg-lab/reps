#!/usr/bin/env python3
"""
Diagnostic script to help locate / import the 'comparaciones' module under C:\REPS\app\pagina.

What it does:
 - Lists files in C:\REPS\app\pagina with repr() to reveal hidden characters.
 - Shows file size, mtime, and first bytes (to detect BOM).
 - Prints whether any filename matches 'comparaciones.py' case-insensitively.
 - Attempts to import any file whose name contains 'comparaciones' (case-insensitive)
   via importlib.util.spec_from_file_location and reports success / exception traceback.
 - Prints Python environment info and sys.path.
 - Lists __pycache__ contents (if present) and shows .pyc filenames.
 - Prints the first 40 lines (text) of any candidate file for quick eyeballing.
 - Does NOT modify any files.

Run:
    python C:\REPS\diagnose_comparaciones.py

Copy & paste the full output back here.

"""
import os
import sys
import traceback
import importlib.util
import importlib.machinery
from pathlib import Path
from datetime import datetime

ROOT = Path(r"C:\REPS")
PKG_DIR = ROOT / "app" / "pagina"

def print_header(title):
    print("\n" + "="*80)
    print(title)
    print("="*80 + "\n")

def safe_read_bytes(p: Path, n=64):
    try:
        with open(p, "rb") as f:
            return f.read(n)
    except Exception as e:
        return f"<error reading bytes: {e}>".encode("utf-8", errors="ignore")

def safe_read_text(p: Path, nlines=40):
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            lines = []
            for i in range(nlines):
                line = f.readline()
                if not line:
                    break
                lines.append(line.rstrip("\n"))
            return lines
    except Exception as e:
        return [f"<error reading text: {e}>"]

def show_dir_listing(p: Path):
    if not p.exists():
        print(f"Directory not found: {p}")
        return []
    names = sorted(os.listdir(p))
    for name in names:
        full = p / name
        try:
            stat = full.stat()
            size = stat.st_size
            mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
        except Exception:
            size = "<stat error>"
            mtime = "<stat error>"
        repr_name = repr(name)
        print(f"{repr_name:60}  {'DIR' if full.is_dir() else 'FILE':4}  size={size:9}  mtime={mtime}")
    return names

def attempt_import(filepath: Path, module_name: str):
    print_header(f"Attempting import of file: {filepath} as module name: {module_name}")
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(filepath))
        if spec is None:
            print("spec_from_file_location returned None")
            return False, "spec None"
        mod = importlib.util.module_from_spec(spec)
        loader = spec.loader
        if loader is None:
            print("spec.loader is None")
            return False, "loader None"
        loader.exec_module(mod)
        print(f"Import OK: module {module_name} loaded from {filepath}")
        # show if run() exists
        if hasattr(mod, "run"):
            print("module has attribute: run")
        else:
            print("module DOES NOT have attribute: run")
        return True, None
    except Exception:
        tb = traceback.format_exc()
        print("IMPORT FAILED with traceback:\n")
        print(tb)
        return False, tb

def main():
    print_header("ENV / PYTHON INFO")
    print(f"Python executable: {sys.executable}")
    print(f"Python version   : {sys.version}")
    print(f"Platform         : {sys.platform}")
    print(f"CWD              : {os.getcwd()}")
    print("sys.path (first 20 entries):")
    for i, p in enumerate(sys.path[:20]):
        print(f"  {i:02d}: {p}")

    print_header(f"Listing files in package directory: {PKG_DIR}")
    names = show_dir_listing(PKG_DIR)

    # show __init__.py content if present
    initp = PKG_DIR / "__init__.py"
    if initp.exists():
        print_header("__init__.py (first lines)")
        for l in safe_read_text(initp, 80):
            print(l)

    print_header("CANDIDATE FILES: operations on files whose name contains 'comparaciones' (case-insensitive)")
    candidates = []
    for name in names:
        if "comparaciones" in name.lower():
            candidates.append(name)

    if not candidates:
        print("No files with 'comparaciones' found in name (case-insensitive).")
    else:
        for name in candidates:
            p = PKG_DIR / name
            print("\n" + "-"*60)
            print(f"Candidate filename repr: {repr(name)} at path: {p}")
            print(f" Is file: {p.is_file()}    Is dir: {p.is_dir()}")
            print(f" First 64 bytes (raw repr): {safe_read_bytes(p, 64)!r}")
            print(f" First 12 lines (utf-8 with replacement):")
            for ln in safe_read_text(p, 12):
                print("   " + ln)
            # Try to import with a safe unique module name
            modname = f"diagnose_comparaciones_impl_{name.replace('.', '_')}"
            ok, info = attempt_import(p, modname)
            if not ok:
                print(f"Import attempt for {name} failed (see above).")

    # list __pycache__ contents
    pycache = PKG_DIR / "__pycache__"
    print_header(f"__pycache__ contents at {pycache}")
    if pycache.exists() and pycache.is_dir():
        for fn in sorted(os.listdir(pycache)):
            print(repr(fn))
    else:
        print("__pycache__ not present")

    # show file types and any hidden extension issues
    print_header("FILES WITH THEIR RAW NAMES (repr) AND ENCODING CHECK")
    for name in names:
        p = PKG_DIR / name
        print(f"\nFile repr: {repr(name)}   Path: {p}")
        if p.is_file():
            first_bytes = safe_read_bytes(p, 8)
            # detect common BOMs
            b = first_bytes
            bom_info = []
            try:
                if b.startswith(b'\xef\xbb\xbf'):
                    bom_info.append("UTF-8 BOM")
                if b.startswith(b'\xff\xfe') or b.startswith(b'\xfe\xff'):
                    bom_info.append("UTF-16 BOM")
                if not bom_info:
                    bom_info = ["no BOM detected"]
            except Exception:
                bom_info = ["error detecting BOM"]
            print("  first bytes repr:", repr(first_bytes))
            print("  BOM info:", ", ".join(bom_info))
        else:
            print("  (not a file)")

    print_header("FINAL NOTE - sanity checks")
    # Does comparisons.py exist exactly (case-sensitive check)
    exact = PKG_DIR / "comparaciones.py"
    exact_exists = exact.exists()
    print(f"Exact path PKG_DIR/comparaciones.py exists? {exact_exists} -> {exact}")
    # show all files lowercased to compare collisions
    lower_map = {}
    for name in names:
        lower_map.setdefault(name.lower(), []).append(name)
    print("\nFiles grouped by lowercase name (to detect case collisions):")
    for k, v in sorted(lower_map.items()):
        if len(v) > 1 or k == "comparaciones.py":
            print(f"  {k!r}: {v}")

    print_header("DONE - paste full output here for analysis")

if __name__ == "__main__":
    main()