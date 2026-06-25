---
title: SentiMind Backend
emoji: 🧠
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# SentiMind — FastAPI Backend

AI-powered mental health & wellness backend (LangGraph + Gemini + audio DSP).
Deployed as a Docker Space on Hugging Face. The Next.js frontend is hosted
separately on Vercel; the database is PostgreSQL on Supabase.

**Health check:** `GET /api/dashboard/health` → `{ "status": "ok" }`

## Required environment variables (set as Space Secrets)
- `DATABASE_URL`, `DIRECT_URL` — Supabase Postgres
- `GEMINI_API_KEY`, `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3`, `GOOGLE_API_KEY`
- `OPENROUTER_API_KEY_*`, `GROQ_API_KEY_*` (optional fallbacks)
- `NEXTAUTH_SECRET` (must match the value used by the Vercel frontend)
- `ALLOWED_ORIGINS` — the Vercel frontend URL, e.g. `https://your-app.vercel.app`
- `TWILIO_*`, `DEEPGRAM_API_KEY` (optional features)
