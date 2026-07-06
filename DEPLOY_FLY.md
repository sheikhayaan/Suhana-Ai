# Deploy Suhana AI On Fly.io

Fly.io is the recommended deployment for the full demo because this app uses AI, image/PDF, voice, and reel workflows that need more memory than many free Flask hosts.

## Why Fly.io

- You can set memory directly in `fly.toml`.
- This repo includes a Dockerfile with `ffmpeg` for media workflows.
- The default config uses `shared-cpu-2x` with `2gb` RAM.
- For a smoother interview demo, scale to `4gb` if reel/video generation still crashes.

## 1. Install Fly CLI

Download and install:

```text
https://fly.io/docs/flyctl/install/
```

Then login:

```powershell
fly auth login
```

## 2. Create App

From the project folder:

```powershell
cd "C:\Users\sheik\Documents\PROJECT AIWORLD"
fly launch --no-deploy
```

When asked:

- App name: choose a unique name, for example `suhana-ai-yourname`
- Region: choose `bom` for India or the nearest region
- Postgres: choose **No** for fastest interview deploy
- Redis: choose **No**

After launch, update `fly.toml` app name if Fly changed it:

```toml
app = "your-real-fly-app-name"
```

## 3. Set Secrets

Use real values:

```powershell
fly secrets set FLASK_SECRET_KEY="your-long-random-secret"
fly secrets set GEMINI_API_KEY="your-gemini-key"
fly secrets set ELEVENLABS_API_KEY="your-elevenlabs-key"
fly secrets set ENCRYPTION_KEY="your-fernet-key"
fly secrets set PUBLIC_BASE_URL="https://your-real-fly-app-name.fly.dev"
```

Optional but recommended:

```powershell
fly secrets set OPENAI_API_KEY="your-openai-key"
fly secrets set GOOGLE_CLIENT_ID="your-google-client-id"
fly secrets set GOOGLE_CLIENT_SECRET="your-google-client-secret"
```

Generate `ENCRYPTION_KEY`:

```powershell
& "C:\Users\sheik\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Generate `FLASK_SECRET_KEY`:

```powershell
& "C:\Users\sheik\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 4. Deploy

```powershell
fly deploy
```

## 5. Check App

```powershell
fly status
fly logs
```

Open:

```text
https://your-real-fly-app-name.fly.dev
```

Check:

```text
https://your-real-fly-app-name.fly.dev/healthz
https://your-real-fly-app-name.fly.dev/readiness
```

`/healthz` should be OK.

`/readiness` may show missing optional keys if you did not configure Google/OpenAI. For best interview demo, at least set Gemini and ElevenLabs.

## 6. If Memory Still Fails

Scale to 4GB:

```powershell
fly scale memory 4096
```

Or edit `fly.toml`:

```toml
[[vm]]
  size = "shared-cpu-2x"
  memory = "4gb"
```

Then:

```powershell
fly deploy
```

## 7. Google OAuth

In Google Cloud Console, add redirect URI:

```text
https://your-real-fly-app-name.fly.dev/auth/google/callback
```

Set:

```powershell
fly secrets set PUBLIC_BASE_URL="https://your-real-fly-app-name.fly.dev"
```

## Interview Demo Flow

Show these in order:

1. Home page
2. Sign up
3. Mission: enter a goal
4. Dashboard
5. AI Tutor
6. AI Quiz
7. Suhana Code
8. Create/Reel
9. Pricing
10. Privacy/Terms

If reel/video is slow, explain:

> Heavy video and voice generation runs through external APIs and is configured at reduced resolution for the live demo environment.
