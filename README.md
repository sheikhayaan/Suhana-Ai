---
title: Suhana AI
emoji: ✨
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Suhana AI

Suhana AI is a Flask-based AI creator studio MVP. It combines account login, script generation, visual generation previews, reel rendering, PDF tools, image tools, credit tracking, BYOK API settings, and a background worker.

## Core Features

- Email/password login and Google OAuth scaffold
- Signed-in reel creation with free usage limits
- AI reel generation from uploaded images, generated image assets, or storyboard placeholders
- Script Generator with Gemini/OpenAI integration and template fallback
- Script-to-Reel flow
- Visual Studio with free image generation plus provider fallbacks
- PDF merger
- Image editor with local edits and OpenAI-ready prompt edit
- User dashboard with credits, jobs, mode, API key count
- Managed credits mode and BYOK mode
- API Vault with encryption wrapper for newly saved keys
- Background/inline worker with pending/processing/completed/failed states
- Credit history and dev credit manager
- Script feedback collection for future model training data

## Architecture

```text
main.py
  Flask routes, database models, auth, tools, billing scaffold

worker.py
  Reusable queue-processing logic

generate_process.py
  Standalone worker runner for production-style separation

text_to_audio.py
  ElevenLabs text-to-speech with silent audio fallback

templates/
  Jinja pages for the product UI

static/
  CSS, images, generated reels, generated tool assets
```

## Run Locally

```powershell
pip install -r requirements.txt
python main.py
```

The development server starts the background worker automatically. For production-style testing, you can run the web app and worker separately:

```powershell
python main.py
python generate_process.py
```

## Deploy

This repo includes `Procfile` and `render.yaml` for Render-style deployment.

```text
Build Command: pip install -r requirements.txt
Start Command: waitress-serve --host=0.0.0.0 --port=$PORT main:app
```

Set production secrets in the hosting dashboard, not in GitHub. Use `.env.example` as the variable checklist.

## Environment Variables

Create `.env`:

```env
FLASK_SECRET_KEY=change_this_to_a_long_secret
ELEVENLABS_API_KEY=
GEMINI_API_KEY=
GEMINI_IMAGE_MODEL=gemini-2.5-flash-image
LEONARDO_API_KEY=
OPENAI_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
ENCRYPTION_KEY=
ENABLE_DEV_ADMIN=0
SESSION_COOKIE_SECURE=1
PROCESS_REELS_INLINE=1
```

For Google OAuth local callback:

```text
http://127.0.0.1:5000/auth/google/callback
http://localhost:5000/auth/google/callback
```

## Credit Model

Managed mode starts each signed-in user with a free allowance:

- AI images: 3 free generations
- AI reels: 5 free generations
- AI scripts: 8 free generations

After the free allowance is used, users can buy managed credits or switch to BYOK mode. BYOK mode skips provider credit consumption and uses saved API keys where supported.

Managed credits are consumed after the free allowance:

- Script generation: 1 credit
- Reel generation: 1 credit
- AI image generation: 1 credit
- Local image edit: 1 credit
- AI image edit: 4 credits

BYOK provider vault:

- Voiceover: ElevenLabs
- Image generation: best-effort free image endpoint first; Leonardo AI, Gemini/Nano Banana, OpenAI, and local placeholder remain as fallbacks
- Video generation: Runway, Pika, and Luma keys can be stored for expansion

## Current Production Gaps

- Replace dev billing with Razorpay or Stripe checkout
- Use a real video provider for AI video generation
- Encrypt existing plaintext API keys or rotate them
- Add CSRF protection
- Add file cleanup lifecycle
- Move generated media to cloud storage
- Use migrations instead of automatic schema patching
- Run web and worker as separate services in production

## CV Summary

Built an AI-powered creator SaaS with Flask, SQLAlchemy, OAuth scaffold, background job processing, FFmpeg video rendering, OpenAI-ready script generation, Gemini Nano Banana image generation, ElevenLabs text-to-speech, BYOK API vault, managed credit accounting, PDF/image tools, and a database-backed reel status pipeline.
