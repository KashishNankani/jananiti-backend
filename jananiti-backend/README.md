# JanaNiti Backend

AI-powered citizen development intelligence platform for Indian MPs — hackathon prototype.

FastAPI + SQLite. No Docker required. Runs locally, deploys to Railway.

## Features

- **Multi-channel citizen intake**: text, voice (transcribed via Groq Whisper), image (analyzed via Gemini Vision), and simulated IVRS.
- **NLP analysis** (Gemini 2.5 Flash): language detection + translation, categorization, urgency/sentiment scoring, keyword extraction.
- **DRFI Engine**: a deterministic, explainable 7-component scoring formula (Development Resource & Fairness Index) that ranks development works per constituency block, independent of the LLM.
- **LLM-generated rankings**: Gemini synthesizes citizen submissions + constituency demographic data into top-5 prioritized recommendations for the MP.
- **Counter-narrative detection**: flags when citizen demand contradicts existing infrastructure data (e.g. demanding a hospital that already exists nearby but is underused).
- **Silent-need detection**: flags underserved blocks with severe demographic deficits but very low citizen reporting.
- **Analytics dashboards**: category/language/sentiment/urgency breakdowns, submission trends, geographic heatmaps.
- **Citizen-facing status tracking**: citizens can check if their submission has been actioned, resolved, or had budget released.

## Setup

```bash
cd jananiti-backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY and GROQ_API_KEY
```

### Getting API keys

- **Gemini**: https://aistudio.google.com/app/apikey (free tier available)
- **Groq**: https://console.groq.com (free tier available, used for Whisper transcription)
- **Sarvam AI** (optional, for higher-quality Indian-language IVRS STT): https://www.sarvam.ai/apis — paid, safe to skip. Falls back to Groq Whisper automatically if `SARVAM_API_KEY` is not set.

## Run

```bash
uvicorn main:app --reload --port 8000
```

On first run, the app automatically:
1. Creates all SQLite tables (`jananiti.db`)
2. Seeds 6 constituency blocks with demographic data
3. Seeds 5 demo user accounts (2 MP, 3 citizen)
4. Seeds ~80 synthetic multilingual citizen submissions

Visit **http://localhost:8000/docs** for interactive Swagger UI to test every endpoint.

## Demo accounts

| Username    | Password    | Role    |
|-------------|-------------|---------|
| mp_sharma   | mp123       | mp      |
| mp_verma    | mp456       | mp      |
| citizen1    | citizen123  | citizen |
| citizen2    | citizen456  | citizen |
| guest       | guest       | citizen |

MP-only endpoints require header: `Authorization: Bearer mp_sharma_token` (token = `{username}_token`).

## Key endpoints

- `POST /auth/login` — get a token
- `POST /submit/text` / `/submit/voice` / `/submit/image` / `/submit/ivrs` — citizen intake
- `GET /submissions` — MP-only, filterable submission list
- `GET /analytics/overview` — dashboard stats
- `GET /analytics/counter_narratives`, `/analytics/silent_needs`, `/analytics/demographics`
- `POST /rankings/generate` — MP-only, runs Gemini + DRFI engine, saves top-5 recommendations
- `GET /rankings/latest`, `/rankings/history`
- `GET /maps/submission_heatmap`, `/maps/block_markers`, `/maps/block/{block_name}`
- `GET /citizen/submissions/{citizen_id}`, `/citizen/public_stats`

## Deploying to Railway

1. Push this folder to a GitHub repo.
2. Create a new Railway project from the repo.
3. Set environment variables `GEMINI_API_KEY` and `GROQ_API_KEY` in Railway's dashboard.
4. Railway auto-detects Python; set the start command to:
   ```
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
5. SQLite file (`jananiti.db`) will live on Railway's ephemeral filesystem — fine for a hackathon demo, but attach a volume if you need persistence across deploys.

## Notes

- Auth is intentionally fake (plain-text passwords, non-expiring string tokens) — this is a hackathon prototype, not production-ready security.
- If `GEMINI_API_KEY` or `GROQ_API_KEY` are missing, the relevant endpoints return HTTP 503 with a clear message rather than crashing.
- Uploaded images are stored in `/uploads`.
