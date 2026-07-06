# Suhana AI Launch Readiness

## Current Launch Spine

- Flask is the main app. Run with `python main.py` locally or Waitress in production.
- New users start at `/mission`, where one goal becomes a guided workspace.
- Dashboard shows credits, recent work, missions, scripts, assets, and saved Tutor/Code outputs.
- Tutor and Suhana Code save logged-in user outputs into `/saved-work/<id>`.
- Pricing is positioned around saved work, exports, credits, tutor/quiz/code/reel value.

## Added Production Checks

- `/healthz` returns lightweight uptime status.
- `/readiness` checks database, secret key, Gemini key, ElevenLabs key, Google OAuth, encryption key, and public base URL.
- Expensive POST routes have a basic in-memory rate limit controlled by:
  - `POST_RATE_LIMIT`
  - `POST_RATE_WINDOW_SECONDS`
- Legal placeholder pages:
  - `/privacy`
  - `/terms`

## Required Before Paid Launch

1. Set production env vars:
   - `FLASK_SECRET_KEY`
   - `GEMINI_API_KEY`
   - `ELEVENLABS_API_KEY`
   - `ENCRYPTION_KEY`
   - `PUBLIC_BASE_URL`
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
2. Replace mock Razorpay with real checkout and webhooks.
3. Review `/privacy` and `/terms` with a lawyer before serious paid usage.
4. Manually test:
   - Signup/login/Google login
   - Mission creation and export
   - Tutor answer, follow-up, saved work, PDF export
   - Quiz generation, scoring, weak/strong analysis, PDF export
   - Suhana Code saved work
   - Reel script, voiceover, and final reel generation
   - PDF tools and image editor
   - Billing/credits
5. For scale, move from SQLite to managed Postgres and move uploaded/generated files to S3 or Cloudinary.

## Local Run

```powershell
cd "C:\Users\sheik\Documents\PROJECT AIWORLD"
python main.py
```

If `python` is not on PATH in Codex, use:

```powershell
& "C:\Users\sheik\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" main.py
```

Open:

```text
http://127.0.0.1:5000
```

## QA Commands

Run these before deployment and after major edits:

```powershell
cd "C:\Users\sheik\Documents\PROJECT AIWORLD"
& "C:\Users\sheik\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m py_compile main.py qa_flask_smoke.py qa_flask_deep.py
& "C:\Users\sheik\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" qa_flask_smoke.py
& "C:\Users\sheik\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" qa_flask_deep.py
```
