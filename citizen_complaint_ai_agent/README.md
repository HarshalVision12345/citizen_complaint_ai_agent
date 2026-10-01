# CivicAI – Citizen Complaint AI Agent

FastAPI + SQLite backend, HTML/CSS/JS frontend. Built for IIIT Naya Raipur Hackathon.
Citizens submit a complaint → AI classifies category, priority, department → trackable ID → officers update status.

## Features (from the IEEE Roadshow deck)
1. **Report** – form, **voice input**, English/Hindi
2. **Understand** – live AI preview of category, priority, department
3. **Classify & Route** – rules engine maps issue to department with SLA
4. **Track** – complaint ID, progress bar, timeline, "My Complaints"
5. **Resolve & Close** – officer updates status; citizen notification logged on every change
- **Duplicate detection** groups repeated reports under one issue (officers see "×N reports")
- **SLA auto-escalation** flags unresolved complaints past SLA (High 4h / Medium 24h / Low 72h)
- **Public analytics dashboard** – resolution rate, avg time, SLA compliance, hotspots

## Run on your laptop
```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate      Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
Open **http://127.0.0.1:8000** (FastAPI serves the website too). API docs: http://127.0.0.1:8000/docs

Officer dashboard PIN: `iiitnr` (change with env var `OFFICER_PIN`).

## Deploy on Render (single service, free)
1. Push this folder to GitHub.
2. Render → New → **Web Service** → pick the repo.
3. Root Directory: `backend`  |  Build: `pip install -r requirements.txt`
4. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Environment variable: `OFFICER_PIN` = your secret PIN.

Note: Render's free disk is temporary, so SQLite data resets on redeploy. For permanent data add a Render Disk and set `DB_PATH=/data/complaints.db`.

## Separate frontend hosting (optional)
Host `frontend/` as a Static Site and set `window.API_BASE = "https://your-backend.onrender.com"` in `frontend/config.js`.

## API
`POST /api/analyze` · `POST /api/complaints` · `GET /api/complaints/{id}` · `GET /api/complaints/lookup?ids=` ·
Officer (header `X-Officer-Pin`): `GET /api/complaints` · `PATCH /api/complaints/{id}/status` · `POST /api/demo`
