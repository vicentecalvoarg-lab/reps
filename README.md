# Dashboard IPS - Modular refactor

This repository layout splits the monolithic Streamlit app into modules.

Directory structure (final expected under your project root, or you can put under C:/REPS):
- app/
  - main.py
  - config.py
  - data.py
  - utils.py
  - standards.py
  - components/
    - filters.py
    - tables.py
  - pages/
    - analysis_ips.py

Setup instructions
1. Create folders:
   - Option A: run the helper script (Windows):
     python create_project_structure.py
     This will create C:\REPS and C:\REPS\data etc.

   - Option B: create folders manually.

2. Place your dataset:
   - Preferred: Parquet file at:
     `C:\REPS\data\output_data.parquet`
   - Or CSV at:
     `C:\REPS\data\output_data.csv`
   - You can override the data directory by setting the environment variable `REPS_DATA_DIR` to another path (e.g. your project path).

3. Install requirements:
   pip install -r requirements.txt

4. Run the app:
   streamlit run app/main.py

Notes
- I preserved the simulation algorithm in `app/pages/analysis_ips.py`. It references the standards in `app/standards.py`.
- The sidebar filters component shows "TODAS" as first option — selecting it means "no filter".
- The code expects certain column names (many variants checked). If your dataset uses different column names, edit `app/pages/analysis_ips.py` to adjust the column detection list (there are comments near the top).
