# BhoomiNiti
Local: `pip install -r requirements.txt && GEMINI_API_KEY=xxx uvicorn app:app --reload` then open http://localhost:8000

Railway: push this folder, set env `GEMINI_API_KEY` (and optional `ADMIN_KEY` for approving contributions, `GEMINI_MODEL`).
Note: Railway disk is ephemeral; attach a Volume for `data/` to keep imports/contributions.

Real data: `data/seed.json` = Lok Sabha USQ 749 (25.07.2023) Annexure-1. Add more with the Import CSV box (columns: state,total_ror,total_villages,clr_villages) - e.g. files downloaded from data.gov.in.
