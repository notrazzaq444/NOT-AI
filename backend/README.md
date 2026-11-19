# NOT Assistant Backend

Starter scaffold for a local personal AI assistant.

## Requirements
- Python 3.11+
- Internet connection for package installation and hosted API calls

## Setup (Windows PowerShell)
```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```
Add your Groq key and a search provider key to `.env`.

## Run
```powershell
python scripts/verify_env.py
python scripts/init_db.py
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000

## Current status
This is a complete starter folder scaffold, not a finished JARVIS assistant. The API health route, static UI, WebSocket connection, SQLite schema, provider wrappers, search clients, and basic utility modules are present. The WebSocket currently returns a setup message; tool calling, real-time search orchestration, streaming, authentication, full voice pipeline, and desktop control still need implementation and testing.

Never expose API keys in frontend code. Keep destructive automation disabled until confirmation and permission handling is implemented.
