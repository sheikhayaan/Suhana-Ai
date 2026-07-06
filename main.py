from flask import Flask, render_template, render_template_string, request, redirect, url_for , session, has_request_context
import uuid
from werkzeug.utils import secure_filename
import os
from config import FLASK_SECRET_KEY, GEMINI_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, LEONARDO_API_KEY, OPENAI_API_KEY, ENCRYPTION_KEY
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash, check_password_hash
import threading
import time
import base64
import json
import shutil
import hashlib
import secrets
import re
import textwrap
import html
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from werkzeug.middleware.proxy_fix import ProxyFix
from markupsafe import Markup

try:
    from authlib.integrations.flask_client import OAuth
except ImportError:
    OAuth = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None

UPLOAD_FOLDER = 'user_uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.config["SECRET_KEY"] = FLASK_SECRET_KEY
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///suhana_ai.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["GOOGLE_CLIENT_ID"] = GOOGLE_CLIENT_ID
app.config["GOOGLE_CLIENT_SECRET"] = GOOGLE_CLIENT_SECRET
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_UPLOAD_MB", "64")) * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"

db = SQLAlchemy(app)
oauth = OAuth(app) if OAuth else None

AI_RESPONSE_CACHE = {}
AI_PROVIDER_FAILURES = {}
RATE_LIMIT_BUCKETS = {}


def ai_cache_get(key, ttl=900):
    item = AI_RESPONSE_CACHE.get(key)
    if not item:
        return None
    created, value = item
    if time.time() - created > ttl:
        AI_RESPONSE_CACHE.pop(key, None)
        return None
    return value


def ai_cache_set(key, value):
    if len(AI_RESPONSE_CACHE) > 120:
        AI_RESPONSE_CACHE.clear()
    AI_RESPONSE_CACHE[key] = (time.time(), value)


def provider_available(provider, ttl=300):
    failed_at = AI_PROVIDER_FAILURES.get(provider)
    return not failed_at or time.time() - failed_at > ttl


def mark_provider_failure(provider):
    AI_PROVIDER_FAILURES[provider] = time.time()


RATE_LIMITED_ENDPOINTS = {
    "studio",
    "mission",
    "startup_analyzer",
    "create",
    "ai_bridge",
    "workflow_builder",
    "creator_copilot",
    "performance_coach",
    "ml_growth_lab",
    "avatar_maker",
    "ai_quiz",
    "site_guide",
    "ai_tutor",
    "suhana_code",
    "pdf_merge",
    "image_editor",
    "script_generator",
    "visual_studio",
    "billing",
}


def client_rate_key():
    user_part = f"user:{session.get('user_id')}" if session.get("user_id") else f"ip:{request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()}"
    return f"{user_part}:{request.endpoint}"


def rate_limit_exceeded(limit=None, window=None):
    if request.method != "POST" or request.endpoint not in RATE_LIMITED_ENDPOINTS:
        return False
    limit = int(os.getenv("POST_RATE_LIMIT", str(limit or 18)))
    window = int(os.getenv("POST_RATE_WINDOW_SECONDS", str(window or 300)))
    now = time.time()
    key = client_rate_key()
    hits = [hit for hit in RATE_LIMIT_BUCKETS.get(key, []) if now - hit < window]
    hits.append(now)
    RATE_LIMIT_BUCKETS[key] = hits
    if len(RATE_LIMIT_BUCKETS) > 1000:
        RATE_LIMIT_BUCKETS.clear()
    return len(hits) > limit

if oauth and GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    generation_mode = db.Column(db.String(30), default="managed")
    google_id = db.Column(db.String(255), nullable=True)
    credits = db.Column(db.Integer, default=0)
    purpose = db.Column(db.String(80), nullable=True)
    primary_goal = db.Column(db.String(220), nullable=True)

class Reel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    folder_id = db.Column(db.String(120), unique=True, nullable=False)
    status = db.Column(db.String(30), default="pending")
    output_file = db.Column(db.String(255), nullable=True)
    error_message = db.Column(db.Text, nullable=True)

class APIKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    key_value = db.Column(db.String(500), nullable=False)

class Script(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, default=0)
    topic = db.Column(db.String(200), nullable=False)
    niche = db.Column(db.String(100), nullable=False)
    tone = db.Column(db.String(100), nullable=False)
    duration = db.Column(db.String(50), nullable=False)
    hook = db.Column(db.Text, nullable=False)
    script_body = db.Column(db.Text, nullable=False)
    scene_plan = db.Column(db.Text, nullable=False)
    caption = db.Column(db.Text, nullable=False)
    hashtags = db.Column(db.Text, nullable=False)
    generation_source = db.Column(db.String(50), default="Template")
    error_message = db.Column(db.Text, nullable=True)

class VisualAsset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, default=0)
    asset_type = db.Column(db.String(50), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    provider = db.Column(db.String(50), default="Fallback")

class CreditTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ScriptFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    script_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, nullable=False, default=0)
    rating = db.Column(db.Integer, nullable=False)
    edited_script = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ExperienceFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, default=0)
    feature = db.Column(db.String(50), nullable=False)
    target_id = db.Column(db.Integer, nullable=True)
    rating = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SavedWork(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, default=0)
    work_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(220), nullable=False)
    prompt = db.Column(db.Text, nullable=True)
    output = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(80), nullable=True)
    href = db.Column(db.String(240), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CreatorPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, default=0)
    niche = db.Column(db.String(160), nullable=False)
    audience = db.Column(db.String(220), nullable=True)
    tone = db.Column(db.String(120), nullable=True)
    goal = db.Column(db.String(220), nullable=True)
    brand_colors = db.Column(db.String(160), nullable=True)
    brand_voice = db.Column(db.String(220), nullable=True)
    plan_body = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(80), default="AI")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BrandMemory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, nullable=False)
    brand_name = db.Column(db.String(160), nullable=True)
    niche = db.Column(db.String(160), nullable=True)
    audience = db.Column(db.String(240), nullable=True)
    colors = db.Column(db.String(180), nullable=True)
    tone = db.Column(db.String(140), nullable=True)
    logo_url = db.Column(db.String(255), nullable=True)
    offer = db.Column(db.String(240), nullable=True)
    content_rules = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


class WorkflowRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, default=0)
    title = db.Column(db.String(180), nullable=False)
    goal = db.Column(db.String(240), nullable=True)
    steps = db.Column(db.Text, nullable=False)
    output_body = db.Column(db.Text, nullable=False)
    script_id = db.Column(db.Integer, nullable=True)
    asset_id = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(40), default="completed")
    source = db.Column(db.String(80), default="AI Workflow")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PerformanceReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, default=0)
    platform = db.Column(db.String(80), nullable=True)
    content_type = db.Column(db.String(80), nullable=True)
    content_url = db.Column(db.String(500), nullable=True)
    metrics = db.Column(db.Text, nullable=False)
    goal = db.Column(db.String(240), nullable=True)
    analysis_body = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(80), default="AI Performance Coach")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MLContentPrediction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, default=0)
    title = db.Column(db.String(180), nullable=False)
    format_type = db.Column(db.String(80), nullable=True)
    hook = db.Column(db.Text, nullable=True)
    audience = db.Column(db.String(240), nullable=True)
    prediction_body = db.Column(db.Text, nullable=False)
    score = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Mission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, default=0)
    title = db.Column(db.String(180), nullable=False)
    role = db.Column(db.String(80), nullable=True)
    goal = db.Column(db.String(260), nullable=False)
    audience = db.Column(db.String(240), nullable=True)
    timeline = db.Column(db.String(80), nullable=True)
    success_metric = db.Column(db.String(240), nullable=True)
    plan_body = db.Column(db.Text, nullable=False)
    tasks_json = db.Column(db.Text, nullable=False)
    progress_json = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(40), default="active")
    source = db.Column(db.String(80), default="Suhana Mission Engine")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


ALLOWED_API_PROVIDERS = {
    "elevenlabs",
    "gemini",
    "leonardo",
    "openai",
    "runway",
    "stability",
    "pika",
    "luma",
}


def ensure_schema():
    db.create_all()

    inspector = inspect(db.engine)
    if "user" in inspector.get_table_names():
        user_columns = [column["name"] for column in inspector.get_columns("user")]
        if "generation_mode" not in user_columns:
            db.session.execute(
                text('ALTER TABLE "user" ADD COLUMN generation_mode VARCHAR(30) DEFAULT "managed"')
            )
            db.session.commit()
        if "google_id" not in user_columns:
            db.session.execute(
                text('ALTER TABLE "user" ADD COLUMN google_id VARCHAR(255)')
            )
            db.session.commit()
        if "credits" not in user_columns:
            db.session.execute(
                text('ALTER TABLE "user" ADD COLUMN credits INTEGER DEFAULT 25')
            )
            db.session.commit()
        if "purpose" not in user_columns:
            db.session.execute(
                text('ALTER TABLE "user" ADD COLUMN purpose VARCHAR(80)')
            )
            db.session.commit()
        if "primary_goal" not in user_columns:
            db.session.execute(
                text('ALTER TABLE "user" ADD COLUMN primary_goal VARCHAR(220)')
            )
            db.session.commit()

    if "reel" in inspector.get_table_names():
        reel_columns = [column["name"] for column in inspector.get_columns("reel")]
        if "error_message" not in reel_columns:
            db.session.execute(
                text("ALTER TABLE reel ADD COLUMN error_message TEXT")
            )
            db.session.commit()

    if "script" in inspector.get_table_names():
        script_columns = [column["name"] for column in inspector.get_columns("script")]
        if "generation_source" not in script_columns:
            db.session.execute(
                text('ALTER TABLE script ADD COLUMN generation_source VARCHAR(50) DEFAULT "Template"')
            )
            db.session.commit()

    if "performance_report" in inspector.get_table_names():
        perf_columns = [column["name"] for column in inspector.get_columns("performance_report")]
        if "content_url" not in perf_columns:
            db.session.execute(
                text("ALTER TABLE performance_report ADD COLUMN content_url VARCHAR(500)")
            )
            db.session.commit()

    if "mission" in inspector.get_table_names():
        mission_columns = [column["name"] for column in inspector.get_columns("mission")]
        if "progress_json" not in mission_columns:
            db.session.execute(
                text("ALTER TABLE mission ADD COLUMN progress_json TEXT")
            )
            db.session.commit()
        if "updated_at" not in mission_columns:
            db.session.execute(
                text("ALTER TABLE mission ADD COLUMN updated_at DATETIME")
            )
            db.session.commit()
        if "error_message" not in script_columns:
            db.session.execute(
                text("ALTER TABLE script ADD COLUMN error_message TEXT")
            )
            db.session.commit()

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


@app.context_processor
def inject_current_user():
    user = None
    if "user_id" in session:
        user = User.query.get(session["user_id"])
    return {
        "current_user": user,
        "csrf_token": get_csrf_token,
        "nim_agent_options": nim_agent_options,
    }


nim_agent_options = [
    {"value": "auto", "label": "Auto best AI"},
    {"value": "nim_nemotron", "label": "NVIDIA Nemotron"},
    {"value": "chatgpt_style", "label": "ChatGPT-style"},
    {"value": "claude_style", "label": "Claude-style"},
    {"value": "deepseek_style", "label": "DeepSeek-style"},
    {"value": "llama_fast", "label": "Llama fast"},
    {"value": "mistral", "label": "Mistral"},
]


def nim_agent_model(agent, feature="text"):
    agent = (agent or "auto").strip()
    feature = (feature or "text").strip()
    env_key = f"NVIDIA_NIM_AGENT_{agent.upper().replace('-', '_')}_{feature.upper()}_MODEL"
    if os.getenv(env_key):
        return os.getenv(env_key)
    mapping = {
        "auto": {
            "code": os.getenv("NVIDIA_NIM_CODE_MODEL", "meta/llama-3.2-3b-instruct"),
            "quiz": os.getenv("NVIDIA_NIM_QUIZ_MODEL", "meta/llama-3.2-3b-instruct"),
            "tutor": os.getenv("NVIDIA_NIM_TUTOR_MODEL", "meta/llama-3.2-3b-instruct"),
            "script": os.getenv("NVIDIA_NIM_CODE_MODEL", "meta/llama-3.2-3b-instruct"),
            "studio": os.getenv("NVIDIA_NIM_TEXT_MODEL", "nvidia/llama-3.1-nemotron-nano-8b-v1"),
            "guide": os.getenv("NVIDIA_NIM_TEXT_MODEL", "nvidia/llama-3.1-nemotron-nano-8b-v1"),
        },
        "nim_nemotron": {"default": "nvidia/llama-3.1-nemotron-nano-8b-v1"},
        "chatgpt_style": {"default": "meta/llama-3.2-3b-instruct"},
        "claude_style": {"default": "mistralai/mistral-small-4-119b-2603"},
        "deepseek_style": {"default": "deepseek-ai/deepseek-coder-6.7b-instruct", "code": "deepseek-ai/deepseek-coder-6.7b-instruct"},
        "llama_fast": {"default": "meta/llama-3.2-3b-instruct"},
        "mistral": {"default": "mistralai/mistral-small-4-119b-2603"},
    }
    selected = mapping.get(agent, mapping["auto"])
    return selected.get(feature) or selected.get("default") or mapping["auto"].get(feature) or os.getenv("NVIDIA_NIM_TEXT_MODEL", "nvidia/llama-3.1-nemotron-nano-8b-v1")


def nim_agent_source(agent, feature_label):
    labels = {item["value"]: item["label"] for item in nim_agent_options}
    return f"{labels.get(agent or 'auto', 'NVIDIA NIM')} {feature_label}"


def get_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


@app.before_request
def protect_post_requests():
    if request.method != "POST":
        return None

    if request.endpoint in {"login", "signup"}:
        return None

    if rate_limit_exceeded():
        return "Too many requests. Please wait a few minutes and try again.", 429

    submitted_token = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
    if not submitted_token or submitted_token != session.get("_csrf_token"):
        return "Security check failed. Refresh the page and try again.", 400

    return None


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Origin-Agent-Cluster"] = "?1"
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"
    if request.endpoint in {"dashboard", "settings", "api_vault", "admin_overview"}:
        response.headers["Cache-Control"] = "no-store, private"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "media-src 'self' blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )
    return response


def unique_items(items):
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def ai_timeout(default=18):
    try:
        return max(4, min(60, int(os.getenv("AI_HTTP_TIMEOUT", str(default)))))
    except ValueError:
        return default


def strict_ai_mode():
    return os.getenv("STRICT_AI_MODE", "0") == "1"


def get_cipher():
    if not Fernet:
        return None

    key = ENCRYPTION_KEY
    if not key:
        digest = hashlib.sha256((FLASK_SECRET_KEY or "dev-secret-key").encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()

    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        return None


def encrypt_secret(value):
    cipher = get_cipher()
    if not cipher or not value:
        return value
    return "enc:" + cipher.encrypt(value.encode()).decode()


def decrypt_secret(value):
    if not value or not value.startswith("enc:"):
        return value
    cipher = get_cipher()
    if not cipher:
        return value
    try:
        return cipher.decrypt(value[4:].encode()).decode()
    except Exception:
        return value


def current_user():
    if "user_id" not in session:
        return None
    return User.query.get(session["user_id"])


def ensure_user_environment(user):
    if not user:
        return

    os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], str(user.id)), exist_ok=True)
    os.makedirs(os.path.join("static", "reels"), exist_ok=True)
    os.makedirs(os.path.join("static", "tools"), exist_ok=True)


def has_credits(user, amount):
    if not user:
        return True
    if user.generation_mode == "byok":
        return True
    return (user.credits or 0) >= amount


def consume_credits(user, amount):
    if not user or user.generation_mode == "byok":
        return
    user.credits = max((user.credits or 0) - amount, 0)
    db.session.add(CreditTransaction(
        user_id=user.id,
        amount=-amount,
        reason="Generation usage"
    ))
    db.session.commit()


FREE_LIMITS = {
    "image": 3,
    "reel": 3,
    "script": 3,
    "video": 3,
}
ADMIN_EMAIL = "sheikhayaan408@gmail.com"
GUEST_FEATURE_LIMIT = 1
STARTER_CREDITS = 0
WELCOME_CREDIT_REASON = "Welcome starter credits"


def usage_count(user, feature):
    if not user:
        return 0
    if os.getenv("DEMO_FRESH_ALLOWANCE", "1") == "1":
        return 0

    if feature == "image":
        return VisualAsset.query.filter_by(
            user_id=user.id,
            asset_type="image"
        ).count()
    if feature == "video":
        return VisualAsset.query.filter_by(
            user_id=user.id,
            asset_type="video"
        ).count()
    if feature == "reel":
        return Reel.query.filter_by(user_id=user.id).count()
    if feature == "script":
        return Script.query.filter_by(user_id=user.id).count()
    return 0


def usage_snapshot(user):
    return {
        feature: {
            "used": usage_count(user, feature),
            "limit": limit,
            "remaining": max(limit - usage_count(user, feature), 0),
        }
        for feature, limit in FREE_LIMITS.items()
    }


def is_admin_user(user):
    return bool(user and (user.email or "").lower() == ADMIN_EMAIL)


def guest_trial_key(feature):
    return f"_guest_trial_used_{feature}"


def guest_trial_used(feature):
    return int(session.get(guest_trial_key(feature), 0) or 0)


def can_guest_generate(feature):
    return guest_trial_used(feature) < GUEST_FEATURE_LIMIT


def record_guest_generation(feature):
    if "user_id" not in session:
        session[guest_trial_key(feature)] = guest_trial_used(feature) + 1


def trial_prompt(feature):
    labels = {
        "image": "AI image generation",
        "reel": "AI reel generation",
        "script": "AI script generation",
        "edit": "image editing",
        "video": "AI video storyboard generation",
    }
    return render_template(
        "trial_prompt.html",
        feature=feature,
        feature_label=labels.get(feature, "AI generation"),
        used=guest_trial_used(feature),
        limit=GUEST_FEATURE_LIMIT,
    )


def can_use_feature(user, feature):
    if not user or user.generation_mode == "byok":
        return True
    if usage_count(user, feature) < FREE_LIMITS.get(feature, 0):
        return True
    return (user.credits or 0) > 0


def charge_after_free_limit(user, feature, used_before, amount=1):
    if not user or user.generation_mode == "byok":
        return
    if used_before >= FREE_LIMITS.get(feature, 0):
        consume_credits(user, amount)


def upgrade_prompt(feature):
    labels = {
        "image": "AI image generation",
        "reel": "AI reel generation",
        "script": "AI script generation",
    }
    return render_template(
        "upgrade_prompt.html",
        feature=feature,
        feature_label=labels.get(feature, "AI generation"),
        limit=FREE_LIMITS.get(feature, 0),
    )


def add_credits(user, amount, reason):
    user.credits = (user.credits or 0) + amount
    db.session.add(CreditTransaction(
        user_id=user.id,
        amount=amount,
        reason=reason
    ))
    db.session.commit()


def grant_welcome_credits_if_needed(user):
    if not user:
        return
    if STARTER_CREDITS <= 0:
        return

    existing = CreditTransaction.query.filter_by(
        user_id=user.id,
        reason=WELCOME_CREDIT_REASON
    ).first()

    if existing:
        return

    current_credits = user.credits or 0
    if current_credits >= STARTER_CREDITS:
        return

    top_up = STARTER_CREDITS - current_credits
    user.credits = STARTER_CREDITS
    db.session.add(CreditTransaction(
        user_id=user.id,
        amount=top_up,
        reason=WELCOME_CREDIT_REASON
    ))
    db.session.commit()


def get_user_api_key(user, provider):
    if not user:
        return None
    saved_key = APIKey.query.filter_by(
        user_id=user.id,
        provider=provider
    ).first()
    if not saved_key:
        return None
    return decrypt_secret(saved_key.key_value)


def openai_key_for_user(user):
    load_dotenv(override=True)
    platform_key = os.getenv("OPENAI_API_KEY") or OPENAI_API_KEY
    if user and user.generation_mode == "byok":
        return get_user_api_key(user, "openai") or platform_key
    return platform_key


def gemini_key_for_user(user):
    load_dotenv(override=True)
    platform_key = os.getenv("GEMINI_API_KEY") or GEMINI_API_KEY
    if user and user.generation_mode == "byok":
        return get_user_api_key(user, "gemini") or platform_key
    return platform_key


def brand_memory_for_user(user):
    if not user:
        return None
    return BrandMemory.query.filter_by(user_id=user.id).first()


def brand_memory_summary(memory):
    if not memory:
        return "No saved brand memory yet. Use clear positioning, consistent colors, and a helpful creator voice."
    parts = [
        f"Brand name: {memory.brand_name or 'Not specified'}",
        f"Niche: {memory.niche or 'Not specified'}",
        f"Audience: {memory.audience or 'Not specified'}",
        f"Colors: {memory.colors or 'Not specified'}",
        f"Tone: {memory.tone or 'Not specified'}",
        f"Offer: {memory.offer or 'Not specified'}",
        f"Rules: {memory.content_rules or 'No rules saved'}",
    ]
    return "\n".join(parts)


def leonardo_key_for_user(user):
    load_dotenv(override=True)
    platform_key = os.getenv("LEONARDO_API_KEY") or LEONARDO_API_KEY
    if user and user.generation_mode == "byok":
        return get_user_api_key(user, "leonardo") or platform_key
    return platform_key


def normalize_ai_text(value):
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "")


def render_ai_markdown(text):
    text = normalize_ai_text(text)
    if not text:
        return Markup("")

    blocks = []
    in_code = False
    code_lang = ""
    code_lines = []
    list_open = False
    table_rows = []

    def inline_markup(value):
        value = html.escape(value)
        value = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", value)
        value = re.sub(r"`(.+?)`", r"<code>\1</code>", value)
        return value

    def close_list():
        nonlocal list_open
        if list_open:
            blocks.append("</ul>")
            list_open = False

    def close_table():
        nonlocal table_rows
        if not table_rows:
            return
        rows = []
        for idx, row in enumerate(table_rows):
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            if idx == 1 and all(re.fullmatch(r":?-{2,}:?", cell.replace(" ", "")) for cell in cells):
                continue
            tag = "th" if idx == 0 else "td"
            rows.append("<tr>" + "".join(f"<{tag}>{inline_markup(cell)}</{tag}>" for cell in cells) + "</tr>")
        blocks.append('<div class="md-table"><table>' + "".join(rows) + "</table></div>")
        table_rows = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                blocks.append(
                    f'<pre><code class="language-{html.escape(code_lang)}">'
                    + html.escape("\n".join(code_lines))
                    + "</code></pre>"
                )
                in_code = False
                code_lang = ""
                code_lines = []
            else:
                close_table()
                close_list()
                in_code = True
                code_lang = stripped[3:].strip()
                code_lines = []
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not stripped:
            close_table()
            close_list()
            continue

        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2:
            close_list()
            table_rows.append(stripped)
            continue

        close_table()

        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            close_list()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{inline_markup(heading.group(2))}</h{level}>")
            continue

        item = re.match(r"^[-*]\s+(.+)$", stripped)
        if item:
            if not list_open:
                blocks.append("<ul>")
                list_open = True
            blocks.append(f"<li>{inline_markup(item.group(1))}</li>")
            continue

        numbered = re.match(r"^\d+\.\s+(.+)$", stripped)
        if numbered:
            if not list_open:
                blocks.append("<ul>")
                list_open = True
            blocks.append(f"<li><strong>{inline_markup(stripped)}</strong></li>")
            continue

        close_list()
        blocks.append(f"<p>{inline_markup(stripped)}</p>")

    if in_code:
        blocks.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
    close_table()
    close_list()
    return Markup("\n".join(blocks))


SUHANA_STARTUP_RESPONSE_STANDARD = """
Suhana startup response standard:
- Be clear enough for a first-time user to understand what this feature does.
- Start with the user's real problem, not generic praise.
- Give a structured output with headings, tables, checklists, and exact next actions.
- Include a practical deliverable the user can use immediately.
- Route the user to the correct Suhana next tool when relevant: Studio, AI Tutor, Suhana Code, Workflow Builder, Creator Copilot, Reel Generator, AI Images, PDF Editor, Performance Coach, or Quiz.
- Avoid vague advice, filler, motivational fluff, and repeated generic AI wording.
- Every answer should feel like a polished startup product output.
"""


def suhana_output_contract(feature):
    return f"""
Required Suhana output contract for {feature}:
1. Problem understood
2. Best answer / deliverable
3. Step-by-step execution
4. Quality checklist
5. Common mistakes or risks
6. Next Suhana tool to open
7. Follow-up prompts the user can ask
"""


def plain_text_from_markdown(text):
    text = re.sub(r"```.*?```", lambda m: m.group(0).strip("`"), text or "", flags=re.S)
    text = re.sub(r"[#*_`>-]", "", text)
    text = re.sub(r"\$\$(.*?)\$\$", r"\1", text, flags=re.S)
    text = re.sub(r"\\\((.*?)\\\)", r"\1", text)
    return html.unescape(text)


def write_text_pdf(title, body, output_path):
    try:
        from PIL import Image, ImageDraw, ImageFont, JpegImagePlugin
    except ImportError:
        return False

    width, height = 1240, 1754
    margin = 86
    line_height = 34
    title_font = ImageFont.load_default()
    body_font = ImageFont.load_default()
    small_font = ImageFont.load_default()
    pages = []
    text = plain_text_from_markdown(body)
    lines = []
    for paragraph in text.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("")
            continue
        wrapped = textwrap.wrap(paragraph, width=92, subsequent_indent="   ") or [""]
        lines.extend(wrapped)

    def new_pdf_page(page_no):
        page = Image.new("RGB", (width, height), (5, 8, 24))
        draw = ImageDraw.Draw(page)
        for i in range(-height, width, 42):
            draw.line((i, 0, i + height, height), fill=(8, 16, 34), width=1)
        draw.rounded_rectangle((48, 48, width - 48, height - 48), radius=42, outline=(31, 78, 110), width=3)
        draw.rounded_rectangle((64, 64, width - 64, 158), radius=28, fill=(8, 15, 36), outline=(52, 211, 153), width=2)
        draw.text((margin, 82), "SUHANA AI", fill=(52, 211, 153), font=small_font)
        draw.text((margin, 112), title[:70], fill=(245, 250, 255), font=title_font)
        draw.text((width - margin - 110, 112), f"Page {page_no}", fill=(125, 211, 252), font=small_font)
        return page, draw

    page_no = 1
    page, draw = new_pdf_page(page_no)
    y = 190
    for line in lines:
        if y > height - 120:
            pages.append(page)
            page_no += 1
            page, draw = new_pdf_page(page_no)
            y = 190
        color = (238, 242, 255)
        if line.isupper() or re.match(r"^\d+\.\s+", line):
            color = (125, 211, 252)
        draw.text((margin, y), line, fill=color, font=body_font)
        y += line_height
    pages.append(page)
    pages[0].save(output_path, save_all=True, append_images=pages[1:])
    return True


def parse_ai_json(text):
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    def loads_ai_json(value):
        try:
            return json.loads(value)
        except ValueError:
            repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", value)
            return json.loads(repaired)

    try:
        return loads_ai_json(cleaned)
    except ValueError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return loads_ai_json(cleaned[start:end + 1])
        raise


def parse_ai_json_array(text):
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    def loads_ai_json(value):
        try:
            return json.loads(value)
        except ValueError:
            repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", value)
            return json.loads(repaired)

    try:
        parsed = loads_ai_json(cleaned)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in ("questions", "quiz", "items"):
                if isinstance(parsed.get(key), list):
                    return parsed[key]
    except ValueError:
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                return loads_ai_json(cleaned[start:end + 1])
            except ValueError:
                return []
    return []


def generate_gemini_script_content(topic, niche, tone, duration, api_key=None):
    load_dotenv(override=True)
    active_gemini_key = (os.getenv("GEMINI_API_KEY") or GEMINI_API_KEY) if api_key is None else api_key

    if not active_gemini_key:
        return None

    prompt = f"""
Generate a premium short-form reel script package as valid JSON only.
Topic: {topic}
Niche: {niche}
Tone: {tone}
Duration: {duration}

Return keys:
hook, script_body, scene_plan, caption, hashtags.
Rules:
- The hook must be sharp and specific.
- The script_body must have clean sections: Hook, Problem, Framework, Example, CTA.
- The scene_plan should use numbered lines with visual direction and text overlay.
- The caption should be ready to post.
- The hashtags field must be a space-separated string, not a list.
"""
    preferred = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
    fallbacks = [] if os.getenv("FAST_AI_MODE", "1") == "1" else ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"]
    try:
        for model in unique_items([preferred] + fallbacks):
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            }
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": active_gemini_key,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=ai_timeout()) as response:
                    response_data = json.loads(response.read().decode("utf-8"))
                text_parts = []
                for candidate in response_data.get("candidates", []):
                    content = candidate.get("content", {})
                    for part in content.get("parts", []):
                        if part.get("text"):
                            text_parts.append(part["text"])

                if not text_parts:
                    continue

                data = parse_ai_json("".join(text_parts))
                return (
                    normalize_ai_text(data.get("hook")),
                    normalize_ai_text(data.get("script_body")),
                    normalize_ai_text(data.get("scene_plan")),
                    normalize_ai_text(data.get("caption")),
                    normalize_ai_text(data.get("hashtags")),
                    f"Gemini {model}",
                    None,
                )
            except Exception as e:
                print(f"Gemini script fallback used for {model}:", e)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError) as e:
        print("Gemini script fallback used:", e)
    return None


def fallback_tutor_lesson(subject, topic, level, style, resources=""):
    return f"""# Suhana Tutor Study Pack

## 0. Problem understood
You want to understand **{topic}** in **{subject}** at **{level}** level using a **{style}** style.

## 1. Simple intuition
Think of {topic} as a system with a few important rules. First understand the meaning, then the formula/process, then solve examples.

## 2. Core concept
Start by defining the topic in your own words. Break it into smaller parts, note why each part matters, and connect it to real life. If this is a science or engineering topic, focus on cause and effect. If it is mathematics, focus on steps and patterns. If it is humanities, focus on meaning, examples, and comparison.

## 3. Formula / rule box
Use textbook-style math whenever needed:
$$a^2 + b^2 = c^2$$
Inline formula example: \\(F = ma\\)

## 4. One solved example
Take one small example from {subject}. Identify what is given, what is asked, which concept applies, and solve it step by step.

## 5. Common mistakes
- Memorizing without understanding the first definition.
- Skipping examples.
- Not checking units, signs, constraints, or assumptions.

## 6. Mini revision notes
Make a short phrase or diagram for the main idea. Revise it once after 10 minutes and again tomorrow.

## 7. Practice questions
- Explain {topic} in 5 lines.
- Solve one easy question.
- Solve one medium question.
- Teach the idea to someone else in 60 seconds.

## 8. Next Suhana workflow
- Open **AI Quiz** to test this topic.
- Ask **AI Tutor** for more solved examples.
- If this is coding/engineering, open **Suhana Code** for implementation practice.

## 9. Follow-up questions you can ask
- What is the definition of {topic}?
- Where is it used?
- What is the most common mistake?
- Can you give one real-life example?
"""


def generate_gemini_tutor_lesson(subject, topic, level, style, resources="", api_key=None):
    load_dotenv(override=True)
    cache_key = "tutor:" + hashlib.sha256("|".join([subject or "", topic or "", level or "", style or "", resources or ""]).encode("utf-8")).hexdigest()
    cached = ai_cache_get(cache_key)
    if cached:
        return cached
    active_gemini_key = (os.getenv("GEMINI_API_KEY") or GEMINI_API_KEY) if api_key is None else api_key
    if not active_gemini_key:
        return None, "Fallback"

    prompt = f"""
You are Suhana AI Tutor Pro, an elite personal teacher for Indian students from class 6 to BTech.
You combine the clarity of the best school teacher, the rigor of a university professor, and the patience of a private tutor.

Create a powerful, polished lesson that is fast to read and easy to use.
Subject: {subject}
Topic: {topic}
Student level: {level}
Preferred teaching style: {style}
Extra resources/context supplied by student: {resources or "None"}

Important output rules:
{SUHANA_STARTUP_RESPONSE_STANDARD}
{suhana_output_contract("AI Tutor")}
- Use Markdown headings.
- Maximize answer quality: reason step-by-step internally, then present a clean final lesson.
- Keep the answer focused: 700-1200 words unless the user explicitly asks for deep detail.
- If the user asks for latest/current facts, say clearly that live web verification is required unless resources provide current data.
- Prefer precise definitions, examples, diagrams, formulas, and exam/interview patterns over generic advice.
- Add a short "Follow-up questions you can ask" section with 3 useful next questions.
- For mathematical formulas, use LaTeX exactly like a maths book:
  - display formulas with $$ ... $$
  - inline formulas with \\( ... \\)
- If the topic is coding, include clean code blocks and complexity analysis.
- If the topic is BTech/engineering, include deeper intuition plus derivations where useful.
- If the topic is class 6-12, keep language age-appropriate but still strong.
- Use diagrams in text when helpful with simple ASCII layouts.
- Be accurate. If resources conflict with standard knowledge, mention the conflict carefully.

Required lesson structure:
# Title
## 0. Problem understood
## 1. Simple intuition
## 2. Core concept
## 3. Formula / rule box
## 4. One solved example
## 5. Common mistakes
## 6. Mini revision notes
## 7. Practice questions
## 8. Next Suhana workflow
## 9. Follow-up questions you can ask
"""
    preferred = os.getenv("GEMINI_TUTOR_MODEL", os.getenv("GEMINI_PRO_MODEL", "gemini-2.5-pro"))
    fallbacks = [] if os.getenv("FAST_AI_MODE", "1") == "1" else ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"]
    for model in unique_items([preferred] + fallbacks):
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": int(os.getenv("GEMINI_TUTOR_MAX_OUTPUT_TOKENS", os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "2200"))),
            },
        }
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": active_gemini_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=ai_timeout()) as response:
                response_data = json.loads(response.read().decode("utf-8"))
            text_parts = []
            for candidate in response_data.get("candidates", []):
                content = candidate.get("content", {})
                for part in content.get("parts", []):
                    if part.get("text"):
                        text_parts.append(part["text"])
            lesson = "\n".join(text_parts).strip()
            if lesson:
                value = (lesson, f"Gemini ({model})")
                ai_cache_set(cache_key, value)
                return value
        except Exception as e:
            if has_request_context():
                session["last_gemini_error"] = str(e)
            print(f"Gemini tutor fallback used for {model}:", e)

    return None, "Fallback"


def generate_gemini_tutor_followup(subject, topic, level, style, previous_answer, question, api_key=None):
    load_dotenv(override=True)
    cache_key = "tutor_follow:" + hashlib.sha256("|".join([subject or "", topic or "", level or "", style or "", previous_answer[:1000] or "", question or ""]).encode("utf-8")).hexdigest()
    cached = ai_cache_get(cache_key)
    if cached:
        return cached
    active_gemini_key = (os.getenv("GEMINI_API_KEY") or GEMINI_API_KEY) if api_key is None else api_key
    if not active_gemini_key:
        return None, "Fallback"
    prompt = f"""
You are Suhana AI Tutor Pro. Answer this follow-up directly and clearly.

Subject: {subject}
Topic: {topic}
Level: {level}
Style: {style}

Previous answer summary/context:
{previous_answer[:3500]}

Student follow-up:
{question}

Rules:
{SUHANA_STARTUP_RESPONSE_STANDARD}
{suhana_output_contract("Creator Copilot")}
- Use Markdown.
- Keep it fast and focused: 300-700 words.
- If maths is needed, use LaTeX with $$...$$ for display formulas and \\(...\\) inline.
- Include one example if useful.
- End with 2 next follow-up questions.
"""
    answer = call_gemini_text(prompt, api_key=active_gemini_key, model_env="GEMINI_TUTOR_MODEL", default_model=os.getenv("GEMINI_TUTOR_MODEL", "gemini-2.5-flash-lite"))
    if answer:
        value = (answer, f"Gemini ({os.getenv('GEMINI_TUTOR_MODEL', 'gemini-2.5-flash-lite')})")
        ai_cache_set(cache_key, value)
        return value
    return None, "Fallback"


def generate_openai_tutor_lesson(subject, topic, level, style, resources="", api_key=None):
    prompt = f"""
You are Suhana AI Tutor Pro. Teach this student with a clear, advanced, textbook-style answer.
Subject: {subject}
Topic: {topic}
Level: {level}
Style: {style}
Resources/context: {resources or "None"}

Rules:
- Use Markdown headings.
- Use LaTeX for maths: display formulas with $$...$$ and inline formulas with \\(...\\).
- Include intuition, core concept, formula box, solved example, common mistakes, revision notes, and quiz.
- If coding/engineering, include clean code, derivation, complexity, and interview notes where useful.
- Keep language easy but powerful.
- If latest/current facts are requested, state that live verification is required unless supplied resources include current data.
- End with 3 strong follow-up questions the student can ask next.
"""
    answer = call_openai_text(prompt, api_key=api_key)
    if answer:
        return answer, "OpenAI Tutor"
    return None, "Fallback"


def generate_deepseek_tutor_lesson(subject, topic, level, style, resources="", ai_agent="auto"):
    prompt = f"""
Subject: {subject}
Topic: {topic}
Student level: {level}
Preferred teaching style: {style}
Extra resources/context supplied by student: {resources or "None"}

Create a polished lesson for an Indian student from class 6 to BTech.

Required structure:
# Title
## 1. Simple intuition
## 2. Core concept
## 3. Formula / rule box
## 4. One solved example
## 5. Common mistakes
## 6. Mini revision notes
## 7. Practice questions
## 8. Follow-up questions you can ask

Rules:
{SUHANA_STARTUP_RESPONSE_STANDARD}
{suhana_output_contract("Workflow Builder")}
- Use Markdown.
- Use LaTeX for maths exactly like a book: display formulas with $$...$$ and inline formulas with \\(...\\).
- If coding/engineering appears, include clean code, derivation or complexity where useful.
- Keep it focused, accurate, and easy to revise.
- End with 3 useful follow-up questions.
"""
    system_prompt = (
        "You are Suhana AI Tutor Pro: a precise, warm, exam-useful teacher. "
        "Think carefully internally, then present a clean final lesson with textbook-quality formulas, examples, and practice."
    )
    answer = call_nvidia_nim_text(
        prompt,
        system_prompt=system_prompt,
        model_env="NVIDIA_NIM_TUTOR_MODEL",
        model_id=nim_agent_model(ai_agent, "tutor"),
        max_tokens=os.getenv("NVIDIA_NIM_TUTOR_MAX_TOKENS", os.getenv("NVIDIA_NIM_MAX_TOKENS", "2800")),
        timeout=int(os.getenv("NVIDIA_NIM_TUTOR_TIMEOUT", "18")),
    )
    if answer:
        return answer, nim_agent_source(ai_agent, "Tutor")
    answer = call_deepseek_text(
        prompt,
        system_prompt=system_prompt,
        max_tokens=os.getenv("DEEPSEEK_TUTOR_MAX_TOKENS", os.getenv("DEEPSEEK_MAX_TOKENS", "2600")),
    )
    if answer:
        return answer, "DeepSeek Tutor"
    return None, "Fallback"


def generate_deepseek_tutor_followup(subject, topic, level, style, previous_answer, question, ai_agent="auto"):
    prompt = f"""
Subject: {subject}
Topic: {topic}
Level: {level}
Style: {style}

Previous answer/context:
{previous_answer[:4000]}

Student follow-up:
{question}

Answer directly with Markdown. Use LaTeX for maths with $$...$$ and \\(...\\).
Keep the answer useful, accurate, and connected to the previous explanation.
End with 2 next follow-up questions.
"""
    system_prompt = (
        "You are Suhana AI Tutor Pro. Answer follow-up questions like a patient expert tutor: "
        "clear, structured, mathematically correct, and practical for exams/interviews."
    )
    answer = call_nvidia_nim_text(
        prompt,
        system_prompt=system_prompt,
        model_env="NVIDIA_NIM_TUTOR_MODEL",
        model_id=nim_agent_model(ai_agent, "tutor"),
        max_tokens=os.getenv("NVIDIA_NIM_TUTOR_MAX_TOKENS", os.getenv("NVIDIA_NIM_MAX_TOKENS", "2200")),
        timeout=int(os.getenv("NVIDIA_NIM_TUTOR_TIMEOUT", "18")),
    )
    if answer:
        return answer, nim_agent_source(ai_agent, "Tutor")
    answer = call_deepseek_text(
        prompt,
        system_prompt=system_prompt,
        max_tokens=os.getenv("DEEPSEEK_TUTOR_MAX_TOKENS", os.getenv("DEEPSEEK_MAX_TOKENS", "2200")),
    )
    if answer:
        return answer, "DeepSeek Tutor"
    return None, "Fallback"


def call_gemini_text(prompt, api_key=None, model_env="GEMINI_TEXT_MODEL", default_model="gemini-2.5-flash"):
    load_dotenv(override=True)
    if has_request_context():
        session.pop("last_gemini_error", None)
    active_gemini_key = (os.getenv("GEMINI_API_KEY") or GEMINI_API_KEY) if api_key is None else api_key
    if not active_gemini_key:
        return None

    preferred = os.getenv(model_env, default_model)
    fallbacks = [] if os.getenv("FAST_AI_MODE", "1") == "1" else ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"]
    for model in unique_items([preferred] + fallbacks):
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.55,
                "maxOutputTokens": int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "2200")),
            },
        }
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": active_gemini_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=ai_timeout()) as response:
                response_data = json.loads(response.read().decode("utf-8"))
            parts = []
            for candidate in response_data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if part.get("text"):
                        parts.append(part["text"])
            answer = "\n".join(parts).strip()
            if answer:
                return answer
        except Exception as e:
            err = str(e)
            if has_request_context():
                session["last_gemini_error"] = err
            print(f"Gemini text fallback used for {model}:", e)
    return None


def call_openai_text(prompt, api_key=None):
    load_dotenv(override=True)
    if os.getenv("OPENAI_TEXT_ENABLED", "1") != "1":
        return None
    active_openai_key = (os.getenv("OPENAI_API_KEY") or OPENAI_API_KEY) if api_key is None else api_key
    if not active_openai_key or not OpenAI:
        return None
    client = OpenAI(api_key=active_openai_key)
    fallbacks = [] if os.getenv("FAST_AI_MODE", "1") == "1" else ["gpt-4.1-mini", "gpt-4o-mini"]
    for model in unique_items([os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini")] + fallbacks):
        try:
            response = client.responses.create(
                model=model,
                input=prompt,
            )
            return response.output_text
        except Exception as e:
            print(f"OpenAI code fallback used for {model}:", e)
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.choices[0].message.content
            except Exception as chat_error:
                print(f"OpenAI chat fallback used for {model}:", chat_error)
    return None


def call_groq_text(prompt, api_key=None, system_prompt=None, json_mode=False):
    load_dotenv(override=True)
    if os.getenv("GROQ_TEXT_ENABLED", "1") != "1":
        return None
    active_key = api_key or os.getenv("GROQ_API_KEY")
    if not active_key:
        return None
    model = os.getenv("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.45,
        "max_tokens": int(os.getenv("GROQ_MAX_TOKENS", "1800")),
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {active_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=ai_timeout()) as response:
            data = json.loads(response.read().decode("utf-8"))
        answer = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
        answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.I | re.S).strip()
        return answer or None
    except Exception as e:
        print("Groq text fallback used:", e)
        return None


def call_deepseek_text(prompt, api_key=None, system_prompt=None, json_mode=False, max_tokens=None):
    load_dotenv(override=True)
    if os.getenv("DEEPSEEK_TEXT_ENABLED", "1") != "1":
        return None
    if not provider_available("deepseek"):
        return None
    active_key = api_key or os.getenv("DEEPSEEK_API_KEY")
    if not active_key:
        return None
    model = os.getenv("DEEPSEEK_TEXT_MODEL", "deepseek-chat")
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(os.getenv("DEEPSEEK_TEMPERATURE", "0.35")),
        "max_tokens": int(max_tokens or os.getenv("DEEPSEEK_MAX_TOKENS", "2400")),
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {active_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=ai_timeout()) as response:
            data = json.loads(response.read().decode("utf-8"))
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip() or None
    except urllib.error.HTTPError as e:
        if json_mode:
            try:
                payload.pop("response_format", None)
                retry_req = urllib.request.Request(
                    "https://api.deepseek.com/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {active_key}",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(retry_req, timeout=ai_timeout()) as response:
                    data = json.loads(response.read().decode("utf-8"))
                answer = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
                answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.I | re.S).strip()
                return answer or None
            except Exception as retry_error:
                print("DeepSeek text fallback used:", retry_error)
                mark_provider_failure("deepseek")
                return None
        print("DeepSeek text fallback used:", e)
        mark_provider_failure("deepseek")
        return None
    except Exception as e:
        print("DeepSeek text fallback used:", e)
        mark_provider_failure("deepseek")
        return None


def call_nvidia_nim_text(prompt, api_key=None, system_prompt=None, json_mode=False, max_tokens=None, model_env="NVIDIA_NIM_TEXT_MODEL", timeout=None, model_id=None):
    load_dotenv(override=True)
    if os.getenv("NVIDIA_NIM_ENABLED", "1") != "1":
        return None
    active_key = api_key or os.getenv("NVIDIA_NIM_API_KEY") or os.getenv("NVIDIA_API_KEY")
    if not active_key:
        return None
    model = model_id or os.getenv(model_env) or os.getenv("NVIDIA_NIM_TEXT_MODEL", "deepseek-ai/deepseek-v4-flash")
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(os.getenv("NVIDIA_NIM_TEMPERATURE", "0.35")),
        "top_p": float(os.getenv("NVIDIA_NIM_TOP_P", "0.9")),
        "max_tokens": int(max_tokens or os.getenv("NVIDIA_NIM_MAX_TOKENS", "2600")),
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        os.getenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1/chat/completions"),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {active_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or ai_timeout()) as response:
            data = json.loads(response.read().decode("utf-8"))
        answer = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
        answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.I | re.S).strip()
        return answer or None
    except urllib.error.HTTPError as e:
        if json_mode:
            try:
                payload.pop("response_format", None)
                retry_req = urllib.request.Request(
                    os.getenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1/chat/completions"),
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {active_key}",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(retry_req, timeout=timeout or ai_timeout()) as response:
                    data = json.loads(response.read().decode("utf-8"))
                answer = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
                answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.I | re.S).strip()
                return answer or None
            except Exception as retry_error:
                print("NVIDIA NIM text fallback used:", retry_error)
                return None
        print("NVIDIA NIM text fallback used:", e)
        return None
    except Exception as e:
        print("NVIDIA NIM text fallback used:", e)
        return None


def call_pollinations_text(prompt):
    if os.getenv("POLLINATIONS_TEXT_ENABLED", "1") != "1":
        return None
    try:
        encoded = urllib.parse.quote(prompt[:12000])
        model = urllib.parse.quote(os.getenv("POLLINATIONS_TEXT_MODEL", "openai"))
        url = f"https://text.pollinations.ai/{encoded}?model={model}"
        req = urllib.request.Request(url, headers={"User-Agent": "SuhanaAI/1.0"}, method="GET")
        with urllib.request.urlopen(req, timeout=ai_timeout(12)) as response:
            text = response.read().decode("utf-8", errors="ignore").strip()
        if text and len(text) > 20:
            return text
    except Exception as e:
        print("Pollinations text fallback used:", e)
    return None


def fallback_code_answer(query, language):
    return f"""# Suhana Code Answer

## 1. Problem understood
{query}

## 2. Best approach
1. Clarify inputs and expected output.
2. Break the problem into smaller states or functions.
3. Choose the simplest data structure.
4. Write clean {language or "code"}.
5. Test edge cases.

## 3. Implementation plan
- Define input/output.
- Write the core function.
- Add validation.
- Test normal, edge, and large cases.

## 4. Quality checklist
- Time complexity
- Space complexity
- Empty input
- Single element
- Large input
- Duplicate values

## 5. Next Suhana workflow
- Use **Suhana Code** follow-up for dry run, optimization, or tests.
- Use **Studio** if this belongs to a larger project or portfolio plan.

## 6. Follow-up prompts
- "Give full code with tests."
- "Dry run with a hard example."
- "Optimize and explain tradeoffs."
"""


def generate_suhana_code_answer(query, language, mode, api_key_gemini=None, api_key_openai=None, previous_answer="", ai_agent="auto"):
    cache_key = "code:" + hashlib.sha256("|".join([query or "", language or "", mode or "", previous_answer[:1000] or "", ai_agent or "auto"]).encode("utf-8")).hexdigest()
    cached = ai_cache_get(cache_key)
    if cached:
        return cached
    prompt = f"""
You are Suhana Code Pro, a senior principal engineer, DSA coach, debugger, and product-minded coding agent.
Your job is to give answers that feel precise, complete, and immediately useful.

Previous answer/context if this is a follow-up:
{previous_answer or "None"}

User query:
{query}

Preferred language: {language}
Mode: {mode}

Response standard:
{SUHANA_STARTUP_RESPONSE_STANDARD}
{suhana_output_contract("Suhana Code")}
- Maximize model capability: reason internally, verify assumptions, and deliver a clean final answer.
- Start with the exact assumption you are making if the prompt is incomplete.
- For DSA: give intuition, algorithm, proof idea, clean code, dry run, complexity, and edge cases.
- For debugging: identify root cause, explain the broken line/pattern, give corrected code, and prevention.
- For project/code generation: give file structure, implementation, setup, testing steps, and security/performance notes.
- For concept explanations: teach from first principles, then show a practical example.
- Prefer production-quality code with clear names, input validation, and comments only where useful.
- Use Markdown headings and fenced code blocks with language names.
- Never hallucinate libraries or APIs. If something depends on versions or missing context, say what to check.
- For latest framework/library behavior, say when current documentation verification is required.
- End with 3 useful follow-up prompts the user can click/ask next.
- End with a short "Next improvement" section when useful.
"""
    code_system_prompt = (
        "You are Suhana Code Pro: a senior engineer, DSA coach, debugger, and systems architect. "
        "Give production-grade answers with assumptions, algorithm, code, dry run, complexity, edge cases, tests, and follow-up prompts."
    )
    nim_code_prompt = f"""
User query:
{query}

Language: {language}
Mode: {mode}
Previous context:
{previous_answer[:1200] or "None"}

Give a direct coding answer with:
1. Assumption
2. Approach
3. Clean code
4. Dry run if useful
5. Time and space complexity
6. Edge cases
7. Tests or validation checklist
8. Next Suhana workflow
9. 3 follow-up prompts

Use Markdown and fenced code blocks. Do not include hidden reasoning or <think> text.
"""
    nim_answer = call_nvidia_nim_text(
        nim_code_prompt,
        system_prompt=code_system_prompt,
        model_env="NVIDIA_NIM_CODE_MODEL",
        model_id=nim_agent_model(ai_agent, "code"),
        max_tokens=os.getenv("NVIDIA_NIM_CODE_MAX_TOKENS", "1400"),
        timeout=int(os.getenv("NVIDIA_NIM_CODE_TIMEOUT", "12")),
    )
    if nim_answer:
        value = (nim_answer, nim_agent_source(ai_agent, "Code"))
        ai_cache_set(cache_key, value)
        return value

    deepseek_answer = call_deepseek_text(
        prompt,
        system_prompt=code_system_prompt,
        max_tokens=os.getenv("DEEPSEEK_CODE_MAX_TOKENS", os.getenv("DEEPSEEK_MAX_TOKENS", "3000")),
    )
    if deepseek_answer:
        value = (deepseek_answer, "DeepSeek Code")
        ai_cache_set(cache_key, value)
        return value

    gemini_answer = call_gemini_text(
        prompt,
        api_key=api_key_gemini,
        model_env="GEMINI_CODE_MODEL",
        default_model=os.getenv("GEMINI_PRO_MODEL", "gemini-2.5-pro"),
    )
    if gemini_answer and os.getenv("DUAL_MODEL_CODE", "0") != "1":
        value = (gemini_answer, "Gemini Pro")
        ai_cache_set(cache_key, value)
        return value

    groq_answer = call_groq_text(
        prompt,
        system_prompt="You are Suhana Code Pro: senior engineer, DSA coach, debugger, and project architect. Give precise Markdown, code blocks, complexity, edge cases, and follow-up prompts.",
    )
    if groq_answer:
        value = (groq_answer, "Groq Code")
        ai_cache_set(cache_key, value)
        return value

    pollinations_answer = call_pollinations_text(prompt)
    if pollinations_answer:
        value = (pollinations_answer, "Pollinations AI")
        ai_cache_set(cache_key, value)
        return value

    openai_answer = call_openai_text(prompt, api_key=api_key_openai)

    if gemini_answer and openai_answer:
        value = (f"""# Suhana Code Dual Model Answer

## Gemini Pro Reasoning
{gemini_answer}

## ChatGPT Cross-Check
{openai_answer}

## Final Recommendation
Use the Gemini answer as the main solution and the ChatGPT section as a second review/check. If they differ, prefer the simpler solution that satisfies the constraints.
""", "Gemini + ChatGPT")
        ai_cache_set(cache_key, value)
        return value
    if gemini_answer:
        value = (gemini_answer, "Gemini Pro")
        ai_cache_set(cache_key, value)
        return value
    if openai_answer:
        value = (openai_answer, "ChatGPT")
        ai_cache_set(cache_key, value)
        return value
    if strict_ai_mode():
        return (
            "## AI provider retry needed\n\nGemini and OpenAI did not return a usable coding answer. "
            "Open `/ai-health` and check key validity, billing/quota, model access, and network. "
            "I am not showing a fake fallback answer because strict AI mode is enabled.",
            "AI Provider Error",
        )
    return fallback_code_answer(query, language), nim_agent_source(ai_agent, "Code")


def generate_site_guide_answer(question, api_key=None, ai_agent="auto"):
    prompt = f"""
You are Suhana AI Website Guide, a friendly support agent inside the Suhana AI website.
Answer in the same language style as the user: English, Hindi, or Hinglish.
Use very easy language, short steps, and point users to exact site sections.

Website map:
- Home: overview of Suhana AI and main tools.
- Tools: list of all creator tools.
- AI Tutor: teaches subjects from class 6 to BTech, supports resources/notes and formulas.
- Suhana Code: coding agent for DSA, debugging, concepts, project generation, optimization, and system design.
- Script Generator: creates hooks, reel scripts, captions, hashtags, and scene plans.
- AI Images: generates images and lets users download/use them.
- AI Reel Generator: creates reels from script/visual idea and voiceover when provider keys work.
- Image Editor: local edits, reel crop, color/contrast, AI prompt edits when OpenAI image billing works.
- PDF Editor: merge PDFs, JPG to PDF, rotate/compress PDFs, compress images.
- API Vault/BYOK: users can connect their own provider keys.
- Dashboard: usage, credits, generated content, account overview.
- Pricing: buy credits or upgrade when free usage is over.
- Login/Signup: saves generations and unlocks free logged-in quota.

User question:
{question}

Rules:
- If user asks "how to use", give 3-6 numbered steps.
- If user asks where something is, give the exact menu/page.
- If a feature depends on external API/billing, say that clearly but positively.
- Keep answer concise, helpful, and investor-demo friendly.
"""
    guide_system_prompt = "You are Suhana AI website guide. Explain features clearly in English, Hindi, or Hinglish. Keep it concise and helpful."
    answer = call_nvidia_nim_text(
        prompt,
        system_prompt=guide_system_prompt,
        model_id=nim_agent_model(ai_agent, "guide"),
        max_tokens=os.getenv("NVIDIA_NIM_GUIDE_MAX_TOKENS", "1400"),
        timeout=int(os.getenv("NVIDIA_NIM_GUIDE_TIMEOUT", "8")),
    )
    if answer:
        return answer, nim_agent_source(ai_agent, "Guide")
    answer = call_deepseek_text(
        prompt,
        system_prompt=guide_system_prompt,
        max_tokens=os.getenv("DEEPSEEK_GUIDE_MAX_TOKENS", "1400"),
    )
    if answer:
        return answer, "DeepSeek"
    answer = call_gemini_text(
        prompt,
        api_key=api_key,
        model_env="GEMINI_GUIDE_MODEL",
        default_model="gemini-2.5-flash",
    )
    if answer:
        return answer, "Gemini"
    answer = call_groq_text(
        prompt,
        system_prompt="You are Suhana AI website guide. Explain features clearly in English, Hindi, or Hinglish. Keep it concise and helpful.",
    )
    if answer:
        return answer, "Groq"
    answer = call_openai_text(prompt)
    if answer:
        return answer, "OpenAI"
    return f"""# Suhana AI Guide

You can use Suhana AI from the Tools menu.

## Quick tour
- Use AI Tutor for study help from class 6 to BTech.
- Use Suhana Code for coding, DSA, debugging, and project help.
- Use Script Generator for reel scripts.
- Use AI Images for image generation.
- Use Create Reel for reel generation.
- Use Image Editor for polishing uploads.
- Use PDF Editor for merge, convert, rotate, and compress tools.

For your question: {question}

Open Tools, choose the matching tool, enter your prompt/upload, and click generate. Login saves your work and gives free credits.
""", "Fallback"


def fallback_quiz(topic, level, count, quiz_type):
    questions = []
    topic_l = (topic or "").lower()
    is_quadratic = "quadratic" in topic_l
    is_dsa = any(word in topic_l for word in ["dsa", "array", "linked", "stack", "queue", "tree", "graph", "recursion", "sorting"])
    if is_quadratic:
        bank = [
            ("For equation x^2 - 5x + 6 = 0, what are the roots?", ["2 and 3", "1 and 6", "-2 and -3", "No real roots"], 0, "Factorization: x^2 - 5x + 6 = (x-2)(x-3)."),
            ("The discriminant of ax^2+bx+c=0 is:", ["b^2 - 4ac", "b^2 + 4ac", "a^2 - 4bc", "2a"], 0, "Discriminant D = b^2 - 4ac."),
            ("If D < 0 for a quadratic equation, roots are:", ["Real and equal", "Real and distinct", "Not real", "Always zero"], 2, "Negative discriminant gives complex/non-real roots."),
            ("Which formula gives roots of ax^2+bx+c=0?", ["(-b ± √(b²-4ac))/2a", "(b ± √D)/2a", "(-a ± √D)/2b", "-c/b"], 0, "This is the standard quadratic formula."),
            ("For x^2 + 4x + 4 = 0, roots are:", ["-2 and -2", "2 and 2", "-4 and 1", "0 and 4"], 0, "It is (x+2)^2 = 0."),
        ]
    elif is_dsa:
        bank = [
            ("Which data structure uses LIFO?", ["Stack", "Queue", "Graph", "Heap"], 0, "Stack uses Last-In First-Out."),
            ("Binary search requires:", ["Sorted data", "Random data", "Linked list only", "No comparisons"], 0, "Binary search works on sorted search space."),
            ("Time complexity of linear search is:", ["O(n)", "O(log n)", "O(1)", "O(n log n)"], 0, "It may inspect every element."),
            ("A queue uses:", ["FIFO", "LIFO", "DFS only", "Hashing only"], 0, "Queue uses First-In First-Out."),
            ("DFS is commonly implemented using:", ["Stack/recursion", "Queue only", "Heap only", "Binary search"], 0, "DFS goes deep using stack behavior."),
        ]
    else:
        bank = [
            (f"What is the first step to master {topic}?", ["Understand the definition", "Memorize random facts", "Skip examples", "Avoid revision"], 0, "Definitions give the base for solving."),
            (f"Which method improves retention for {topic}?", ["Practice with feedback", "Only reading once", "Ignoring mistakes", "No examples"], 0, "Active practice reveals weak points."),
            (f"What should you do after learning a formula/concept in {topic}?", ["Solve examples", "Close the book", "Change topic immediately", "Avoid questions"], 0, "Examples convert theory into skill."),
            (f"What is a common mistake in {topic}?", ["Skipping basics", "Checking answers", "Writing steps", "Revising"], 0, "Weak basics cause most errors."),
            (f"Best revision method for {topic}?", ["Short notes + questions", "Long passive reading only", "No testing", "Random scrolling"], 0, "Notes plus questions improve recall."),
        ]
    for i in range(1, count + 1):
        q, options, answer, explanation = bank[(i - 1) % len(bank)]
        shift = (i - 1) % 4
        rotated_options = options[shift:] + options[:shift]
        rotated_answer = (answer - shift) % 4
        questions.append({
            "question": q if i <= len(bank) else f"{topic}: applied practice question {i}. {q}",
            "options": rotated_options,
            "answer": rotated_answer,
            "explanation": explanation,
            "difficulty": "Medium" if i % 3 else "Hard",
            "weak_area": "Formula/application" if is_quadratic else ("DSA fundamentals" if is_dsa else "Concept clarity"),
        })
    return questions


def generate_quiz_questions(topic, level, count, quiz_type, api_key=None, ai_agent="auto"):
    prompt = f"""
Create a strict test quiz as JSON only.
Topic: {topic}
Level: {level}
Quiz type: {quiz_type}
Number of questions: {count}

Return a JSON array. Each item must contain:
question, options (4 strings), answer (0-3), explanation, difficulty (Easy/Medium/Hard), weak_area.

Make it like a serious exam: class 10 to BTech, tech interview, DSA, placement, or advanced depending on user input.
Make explanations diagnose weak areas and recommend the next Suhana workflow: AI Tutor for revision, Suhana Code for DSA/project practice, or Studio for a full learning plan.
No markdown. JSON only.
"""
    quiz_system_prompt = "You create strict exam quizzes. Return valid JSON only, no markdown. Ensure the answer index is 0-based and correct."
    nim_quiz_prompt = (
        f"Create {count} MCQ questions about {topic} for {level}. "
        f"Quiz type: {quiz_type}. Return a JSON array only. "
        "Each object has question, options array of 4 strings, answer integer 0-3, "
        "explanation, difficulty, weak_area. No markdown."
    )
    text_answer = call_nvidia_nim_text(
        nim_quiz_prompt,
        system_prompt=quiz_system_prompt,
        json_mode=False,
        model_env="NVIDIA_NIM_QUIZ_MODEL",
        model_id=nim_agent_model(ai_agent, "quiz"),
        max_tokens=os.getenv("NVIDIA_NIM_QUIZ_MAX_TOKENS", "600"),
        timeout=int(os.getenv("NVIDIA_NIM_QUIZ_TIMEOUT", "14")),
    )
    source = nim_agent_source(ai_agent, "Quiz")
    if not text_answer:
        text_answer = call_deepseek_text(
        prompt,
        system_prompt=quiz_system_prompt,
        json_mode=True,
        max_tokens=os.getenv("DEEPSEEK_QUIZ_MAX_TOKENS", "2600"),
        )
        source = "DeepSeek Quiz"
    if not text_answer:
        text_answer = call_gemini_text(prompt, api_key=api_key, model_env="GEMINI_QUIZ_MODEL", default_model="gemini-2.5-flash")
        source = "Gemini Quiz"
    if not text_answer:
        text_answer = call_groq_text(
            prompt,
            system_prompt="You create strict exam quizzes. Return valid JSON only, no markdown.",
            json_mode=True,
        )
        source = "Groq Quiz"
    if not text_answer:
        text_answer = call_openai_text(prompt)
        source = "OpenAI Quiz"
    parsed = parse_ai_json_array(text_answer)
    if parsed:
        normalized = []
        for item in parsed[:count]:
            if not isinstance(item, dict):
                continue
            options = item.get("options") or []
            if len(options) < 4:
                continue
            raw_answer = item.get("answer", item.get("correct_answer", item.get("correct", 0)))
            answer_index = 0
            if isinstance(raw_answer, int):
                answer_index = raw_answer
            elif str(raw_answer).strip().isdigit():
                answer_index = int(str(raw_answer).strip())
            elif str(raw_answer).strip().upper() in {"A", "B", "C", "D"}:
                answer_index = ord(str(raw_answer).strip().upper()) - ord("A")
            else:
                for opt_idx, option in enumerate(options[:4]):
                    if str(raw_answer).strip().lower() == str(option).strip().lower():
                        answer_index = opt_idx
                        break
            if answer_index == 4:
                answer_index = 3
            answer_index = max(0, min(answer_index, 3))
            normalized.append({
                "question": normalize_ai_text(item.get("question")),
                "options": [normalize_ai_text(option) for option in options[:4]],
                "answer": answer_index,
                "explanation": normalize_ai_text(item.get("explanation")),
                "difficulty": normalize_ai_text(item.get("difficulty") or "Medium"),
                "weak_area": normalize_ai_text(item.get("weak_area") or "Concept clarity"),
            })
        if normalized:
            return normalized[:count], source
    if text_answer and source.startswith(("Auto", "NVIDIA", "ChatGPT-style", "Claude-style", "DeepSeek-style", "Llama", "Mistral")):
        return fallback_quiz(topic, level, count, quiz_type), source
    return fallback_quiz(topic, level, count, quiz_type), nim_agent_source(ai_agent, "Quiz")


def analyze_quiz_result(questions, answers):
    correct = 0
    weak = {}
    strong = {}
    difficulty = {"Easy": [0, 0], "Medium": [0, 0], "Hard": [0, 0]}
    review = []
    for idx, q in enumerate(questions):
        selected = answers.get(str(idx))
        options = q.get("options") or []
        raw_expected = q.get("answer", 0)
        expected_candidates = set()
        if isinstance(raw_expected, int):
            expected_candidates.add(raw_expected)
        else:
            raw = str(raw_expected).strip()
            if raw.isdigit():
                val = int(raw)
                expected_candidates.add(val - 1 if 1 <= val <= 4 else val)
            elif raw.upper() in {"A", "B", "C", "D"}:
                expected_candidates.add(ord(raw.upper()) - ord("A"))
            else:
                for opt_idx, option in enumerate(options):
                    if raw.lower() == str(option).strip().lower():
                        expected_candidates.add(opt_idx)
        if not expected_candidates:
            expected_candidates.add(0)
        selected_int = int(selected) if selected is not None and str(selected).isdigit() else None
        expected = sorted(expected_candidates)[0]
        is_correct = selected_int is not None and selected_int in expected_candidates
        correct += 1 if is_correct else 0
        area = q.get("weak_area", "Mixed concepts")
        diff = q.get("difficulty", "Medium")
        difficulty.setdefault(diff, [0, 0])
        difficulty[diff][1] += 1
        if is_correct:
            difficulty[diff][0] += 1
            strong[area] = strong.get(area, 0) + 1
        else:
            weak[area] = weak.get(area, 0) + 1
        selected_text = options[selected_int] if selected_int is not None and 0 <= selected_int < len(options) else ""
        correct_text = options[expected] if 0 <= expected < len(options) else str(raw_expected)
        review.append({
            "index": idx + 1,
            "question": q,
            "selected": selected,
            "selected_text": selected_text,
            "correct_text": correct_text,
            "correct": is_correct,
        })
    weak_sorted = sorted(weak.items(), key=lambda item: item[1], reverse=True)
    strong_sorted = sorted(strong.items(), key=lambda item: item[1], reverse=True)
    if correct == len(questions):
        verdict = "Excellent. You understood this quiz well. Revise once and try a harder test."
    elif correct >= max(1, int(len(questions) * 0.7)):
        verdict = "Good base. Fix the weak areas below and attempt a harder quiz."
    elif correct >= max(1, int(len(questions) * 0.4)):
        verdict = "Average. You know some parts, but need focused revision before moving ahead."
    else:
        verdict = "Weak foundation. Start with a simple lesson, then retry a smaller quiz."
    next_actions = []
    if weak_sorted:
        top_weak = weak_sorted[0][0]
        next_actions = [
            f"Revise {top_weak} in AI Tutor.",
            "Retry a 5-question quiz only on the weak area.",
            "Write short notes from every wrong explanation.",
        ]
    else:
        next_actions = [
            "Try a harder quiz with more applied questions.",
            "Export this result as PDF for record.",
            "Use AI Tutor for advanced examples.",
        ]
    export_lines = [
        "Suhana AI Quiz Analysis",
        f"Score: {correct}/{len(questions)} ({round((correct / max(len(questions), 1)) * 100)}%)",
        f"Verdict: {verdict}",
        "",
        "Strong Areas:",
    ]
    export_lines += [f"- {area}: {count} correct" for area, count in strong_sorted] or ["- No strong area detected yet"]
    export_lines += [
        "",
        "Weak Areas:",
    ]
    export_lines += [f"- {area}: {count}" for area, count in weak_sorted] or ["- No major weak area"]
    export_lines.append("\nNext Actions:")
    export_lines += [f"- {action}" for action in next_actions]
    export_lines.append("\nQuestion Review:")
    for item in review:
        q = item["question"]
        export_lines.append(f"\nQ{item['index']}. {q.get('question')}")
        export_lines.append(f"Your answer: {item['selected_text'] or 'Not answered'}")
        export_lines.append(f"Correct answer: {item['correct_text']}")
        export_lines.append(f"Explanation: {q.get('explanation', '')}")
    export_lines.append("\nNext Suhana Workflow: Open AI Tutor for weak areas, then regenerate a focused quiz.")
    return {
        "correct": correct,
        "total": len(questions),
        "percent": round((correct / max(len(questions), 1)) * 100),
        "weak": weak_sorted,
        "strong": strong_sorted,
        "verdict": verdict,
        "next_actions": next_actions,
        "difficulty": difficulty,
        "review": review,
        "export_text": "\n".join(export_lines),
    }


def ai_provider_health():
    load_dotenv(override=True)
    checks = []
    gemini_key = os.getenv("GEMINI_API_KEY") or GEMINI_API_KEY
    openai_key = os.getenv("OPENAI_API_KEY") or OPENAI_API_KEY
    groq_key = os.getenv("GROQ_API_KEY")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    nim_key = os.getenv("NVIDIA_NIM_API_KEY") or os.getenv("NVIDIA_API_KEY")

    nim_status = {"provider": "NVIDIA NIM", "configured": bool(nim_key), "ok": False, "message": "Missing NVIDIA_NIM_API_KEY"}
    if nim_key:
        answer = call_nvidia_nim_text("Reply with exactly: OK", api_key=nim_key, max_tokens=40)
        nim_status.update(ok=bool(answer), message=(answer or "NVIDIA NIM request failed. Check key, credits/quota, model name, or server network."))
    checks.append(nim_status)

    deepseek_status = {"provider": "DeepSeek", "configured": bool(deepseek_key), "ok": False, "message": "Missing DEEPSEEK_API_KEY"}
    if deepseek_key:
        answer = call_deepseek_text("Reply with exactly: OK", api_key=deepseek_key, max_tokens=40)
        deepseek_status.update(ok=bool(answer), message=(answer or "DeepSeek request failed. Check key, balance/quota, model name, or server network."))
    checks.append(deepseek_status)

    gemini_status = {"provider": "Gemini", "configured": bool(gemini_key), "ok": False, "message": "Missing GEMINI_API_KEY"}
    if gemini_key:
        answer = call_gemini_text("Reply with exactly: OK", api_key=gemini_key, default_model=os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash"))
        gemini_status.update(ok=bool(answer), message=(answer or "Gemini request failed. Check key, billing/quota, model name, or server network."))
    checks.append(gemini_status)

    openai_status = {"provider": "OpenAI", "configured": bool(openai_key), "ok": False, "message": "Missing OPENAI_API_KEY"}
    if openai_key:
        answer = call_openai_text("Reply with exactly: OK", api_key=openai_key)
        openai_status.update(ok=bool(answer), message=(answer or "OpenAI request failed. Check key, billing/quota, model name, or server network."))
    checks.append(openai_status)
    groq_status = {"provider": "Groq", "configured": bool(groq_key), "ok": False, "message": "Missing GROQ_API_KEY"}
    if groq_key:
        answer = call_groq_text("Reply with exactly: OK", api_key=groq_key)
        groq_status.update(ok=bool(answer), message=(answer or "Groq request failed. Check key, quota, model name, or server network."))
    checks.append(groq_status)
    return checks


def generate_script_content(topic, niche, tone, duration, api_key=None, ai_agent="auto"):
    topic = (topic or "your idea").strip()
    niche = (niche or "Creator").strip()
    tone = (tone or "Professional").strip()
    duration = (duration or "30 seconds").strip()

    deepseek_prompt = f"""
Generate a premium short-form reel script package as valid JSON only.
Topic: {topic}
Niche: {niche}
Tone: {tone}
Duration: {duration}

Return only these keys:
hook, script_body, scene_plan, caption, hashtags.

Quality rules:
{SUHANA_STARTUP_RESPONSE_STANDARD}
- Make the hook scroll-stopping but believable.
- Script must match the duration and sound natural for voiceover.
- Scene plan must be numbered and visual enough for reel generation.
- Caption should feel creator-ready.
- Hashtags can be a string or array.
- Include a clear CTA and route to the next Suhana workflow where natural.
"""
    script_system_prompt = "You are Suhana Script Pro, a viral short-form strategist. Return clean JSON only with no markdown."
    nim_script_prompt = f"""
Return JSON only. No explanation.
Topic: {topic}
Niche: {niche}
Tone: {tone}
Duration: {duration}
Keys: hook, script_body, scene_plan, caption, hashtags.
Keep script_body under 120 words. Make it creator-ready and natural for voiceover.
"""
    nim_answer = call_nvidia_nim_text(
        nim_script_prompt,
        system_prompt=script_system_prompt,
        json_mode=False,
        model_id=nim_agent_model(ai_agent, "script"),
        max_tokens=os.getenv("NVIDIA_NIM_SCRIPT_MAX_TOKENS", "650"),
        timeout=int(os.getenv("NVIDIA_NIM_SCRIPT_TIMEOUT", "18")),
    )
    if nim_answer:
        try:
            data = parse_ai_json(nim_answer)
            if not isinstance(data, dict) or not data.get("hook") or not data.get("script_body"):
                raise ValueError("NIM script JSON did not include required script fields")
            return (
                normalize_ai_text(data.get("hook")),
                normalize_ai_text(data.get("script_body")),
                normalize_ai_text(data.get("scene_plan")),
                normalize_ai_text(data.get("caption")),
                normalize_ai_text(data.get("hashtags")),
                nim_agent_source(ai_agent, "Script"),
                None,
            )
        except Exception as e:
            print("NVIDIA NIM script fallback parse failed:", e)
            if nim_answer and len(nim_answer.strip()) > 40:
                return (
                    f"Watch this before you try {topic}.",
                    normalize_ai_text(nim_answer),
                    f"1. Open with the hook about {topic}\n2. Show the main mistake\n3. Give the best tip\n4. Show a quick example\n5. End with a save/share CTA",
                    f"Save this {niche.lower()} guide for your next {duration} reel.",
                    f"#{niche.replace(' ', '')} #SuhanaAI #CreatorTips",
                    nim_agent_source(ai_agent, "Script"),
                    None,
                )

    deepseek_answer = call_deepseek_text(
        deepseek_prompt,
        system_prompt=script_system_prompt,
        json_mode=True,
        max_tokens=os.getenv("DEEPSEEK_SCRIPT_MAX_TOKENS", "1800"),
    )
    if deepseek_answer:
        try:
            data = parse_ai_json(deepseek_answer)
            return (
                normalize_ai_text(data.get("hook")),
                normalize_ai_text(data.get("script_body")),
                normalize_ai_text(data.get("scene_plan")),
                normalize_ai_text(data.get("caption")),
                normalize_ai_text(data.get("hashtags")),
                "DeepSeek",
                None,
            )
        except Exception as e:
            print("DeepSeek script fallback parse failed:", e)

    gemini_result = generate_gemini_script_content(
        topic, niche, tone, duration, api_key=api_key
    )
    if gemini_result:
        return gemini_result

    load_dotenv(override=True)
    active_openai_key = os.getenv("OPENAI_API_KEY") or OPENAI_API_KEY

    if os.getenv("OPENAI_TEXT_ENABLED", "1") == "1" and active_openai_key and OpenAI:
        try:
            client = OpenAI(api_key=active_openai_key)
            prompt = f"""
Generate a short-form reel script package as valid JSON only.
Topic: {topic}
Niche: {niche}
Tone: {tone}
Duration: {duration}

Return keys:
hook, script_body, scene_plan, caption, hashtags.
The scene_plan should use numbered lines.
"""
            response = client.responses.create(
                model=os.getenv("OPENAI_TEXT_MODEL", "gpt-5"),
                input=prompt,
            )
            data = json.loads(response.output_text)
            return (
                normalize_ai_text(data.get("hook")),
                normalize_ai_text(data.get("script_body")),
                normalize_ai_text(data.get("scene_plan")),
                normalize_ai_text(data.get("caption")),
                normalize_ai_text(data.get("hashtags")),
                "OpenAI",
                None,
            )
        except Exception as e:
            print("OpenAI script fallback used:", e)
            fallback_error = str(e)
    else:
        fallback_error = None

    groq_prompt = f"""
Generate a premium short-form reel script package as valid JSON only.
Topic: {topic}
Niche: {niche}
Tone: {tone}
Duration: {duration}
Return keys: hook, script_body, scene_plan, caption, hashtags.
Make it practical, punchy, and creator-ready.
"""
    groq_answer = call_groq_text(
        groq_prompt,
        system_prompt="You are a viral short-form content strategist. Return valid JSON only.",
        json_mode=True,
    )
    if groq_answer:
        try:
            data = parse_ai_json(groq_answer)
            return (
                normalize_ai_text(data.get("hook")),
                normalize_ai_text(data.get("script_body")),
                normalize_ai_text(data.get("scene_plan")),
                normalize_ai_text(data.get("caption")),
                normalize_ai_text(data.get("hashtags")),
                "Groq",
                None,
            )
        except Exception as e:
            print("Groq script fallback parse failed:", e)

    pollinations_prompt = f"""
Generate a premium short-form reel script package as JSON only.
Topic: {topic}
Niche: {niche}
Tone: {tone}
Duration: {duration}
Return keys: hook, script_body, scene_plan, caption, hashtags.
"""
    pollinations_answer = call_pollinations_text(pollinations_prompt)
    if pollinations_answer:
        try:
            data = parse_ai_json(pollinations_answer)
            return (
                normalize_ai_text(data.get("hook")),
                normalize_ai_text(data.get("script_body")),
                normalize_ai_text(data.get("scene_plan")),
                normalize_ai_text(data.get("caption")),
                normalize_ai_text(data.get("hashtags")),
                "Pollinations AI",
                None,
            )
        except Exception:
            lines = pollinations_answer.strip()
            return (
                f"Watch this before you try {topic}.",
                lines,
                f"1. Hook text: {topic}\n2. Show the problem\n3. Explain the framework\n4. Show example\n5. CTA",
                f"Save this {niche.lower()} framework and use it today.",
                f"#{niche.replace(' ', '')} #Reels #SuhanaAI",
                "Pollinations AI",
                None,
            )

    if strict_ai_mode():
        error_text = fallback_error or "Gemini/OpenAI did not return a usable script. Check /ai-health, quota, model access, or network."
        return (
            "AI provider retry needed",
            error_text,
            "No scene plan generated because real AI providers failed.",
            "Please retry after checking AI provider health.",
            "#SuhanaAI #Retry",
            "AI Provider Error",
            error_text,
        )

    tone_hooks = {
        "Professional": f"Most people misunderstand {topic}. Here is the clear version.",
        "Funny": f"If {topic} still confuses you, congratulations, this reel is your rescue mission.",
        "Luxury": f"The smartest creators treat {topic} differently. Here is the premium approach.",
        "Emotional": f"If {topic} matters to you, this could change how you start today.",
        "Hinglish": f"Agar {topic} ko simple banana hai, yeh reel save kar lo.",
        "Bold": f"Stop doing {topic} the hard way. Try this instead.",
    }

    hook = tone_hooks.get(tone, tone_hooks["Professional"])

    duration_beats = {
        "15 seconds": ["Problem", "Simple fix", "Call to action"],
        "30 seconds": ["Hook", "Problem", "Insight", "Example", "Call to action"],
        "60 seconds": ["Hook", "Problem", "Common mistake", "Framework", "Example", "Proof", "Call to action"],
    }
    beats = duration_beats.get(duration, duration_beats["30 seconds"])

    script_lines = [
        f"Hook: {hook}",
        f"Problem: In the {niche} space, people often make {topic} feel more complicated than it is.",
        f"Insight: The fastest way to improve is to focus on one clear action instead of ten random tips.",
        f"Example: Show one visual example of how {topic} looks before and after applying the idea.",
        "CTA: Save this reel and try it in your next piece of content.",
    ]

    if tone == "Funny":
        script_lines[1] = f"Problem: Everyone talks about {topic} like it needs a PhD and three coffees."
    elif tone == "Luxury":
        script_lines[2] = "Insight: Premium results come from precision, restraint, and consistency."
    elif tone == "Hinglish":
        script_lines = [
            f"Hook: {hook}",
            f"Problem: {niche} mein log {topic} ko unnecessarily complicated bana dete hain.",
            "Insight: Ek simple action choose karo, usko consistently repeat karo.",
            f"Example: Screen par before/after dikhao jahan {topic} clearly improve hota hai.",
            "CTA: Is reel ko save karo aur apne next content mein try karo.",
        ]

    scene_plan = "\n".join(
        f"Scene {index + 1}: {beat} - show a clean visual, short caption, and fast cut."
        for index, beat in enumerate(beats)
    )

    caption = f"{topic} becomes easier when you simplify the first step. Save this for your next {niche.lower()} idea."
    hashtags = " ".join([
        f"#{niche.replace(' ', '')}",
        "#AIContent",
        "#Reels",
        "#CreatorTools",
        "#SuhanaAI",
    ])

    return hook, "\n".join(script_lines), scene_plan, caption, hashtags, nim_agent_source(ai_agent, "Script"), fallback_error


def fallback_creator_plan(niche, audience, tone, goal, brand_colors, brand_voice):
    days = []
    pillars = ["Educate", "Trust", "Proof", "Behind the scenes", "Offer", "Community"]
    for day in range(1, 31):
        pillar = pillars[(day - 1) % len(pillars)]
        days.append(
            f"| Day {day} | {pillar} | Reel: {niche} tip for {audience or 'your audience'} | "
            f"Hook: Stop guessing about {niche}. Try this. | Visual: {brand_colors or 'clean brand colors'} "
            f"with product/person demo | CTA: Save, comment, or DM for next step |"
        )
    return f"""# 30-Day Creator Copilot Plan

## Brand Memory
- Niche: {niche}
- Audience: {audience or "General audience"}
- Tone: {tone or "Professional"}
- Goal: {goal or "Grow audience and generate leads"}
- Colors: {brand_colors or "Use clean high-contrast brand palette"}
- Voice: {brand_voice or "Clear, confident, helpful"}

## Content Pillars
1. Education
2. Trust and proof
3. Relatable mistakes
4. Behind the scenes
5. Offer and conversion
6. Community engagement

## 30-Day Calendar
| Day | Pillar | Idea | Hook | Visual Direction | CTA |
|---|---|---|---|---|---|
{chr(10).join(days)}

## Weekly Workflow
- Monday: batch scripts.
- Tuesday: generate visuals.
- Wednesday: record/voiceover.
- Thursday: edit reels.
- Friday-Sunday: post, reply, and analyze.

## Next Actions
- Turn Day 1 into a script.
- Generate the Day 1 image visual.
- Create a reel from the script and image.
"""


def generate_creator_copilot_plan(niche, audience, tone, goal, brand_colors, brand_voice, api_key=None, ai_agent="auto"):
    prompt = f"""
You are Suhana Creator Copilot, a strategic content operator for creators, startups, agencies, coaches, and educators.
Create a premium 30-day content operating plan that feels like a real creator operating system, not generic advice.

Inputs:
- Niche: {niche}
- Target audience: {audience or "Not specified"}
- Tone/style: {tone or "Professional"}
- Business/content goal: {goal or "Grow audience and generate leads"}
- Brand colors: {brand_colors or "Not specified"}
- Brand voice: {brand_voice or "Clear, confident, helpful"}

Rules:
{SUHANA_STARTUP_RESPONSE_STANDARD}
{suhana_output_contract("Studio Strategy Composer")}
- Use Markdown.
- Start with a sharp positioning summary.
- Include a section called "## Brand Memory Snapshot".
- Include a section called "## 30-Day Execution Calendar" with a Markdown table.
- Make every day actionable and specific.
- Each table row must be compact: day, pillar, reel idea, hook, visual prompt, CTA.
- Include "## Weekly Production Workflow" with batching steps.
- Include "## Performance Coach" with metrics, what to improve, and decision rules.
- Include "## Reusable Templates" with 3 plug-and-play scripts/hooks.
- Include "## Next Best Actions" with exact Suhana tools to use next.
- Keep it ambitious but realistic for one creator.
- Do not make generic advice; every idea must fit the niche and audience.
- Keep the complete answer under 2500 words.
"""
    creator_system_prompt = (
        "You are Suhana Creator Copilot: a sharp creator operator for startups and agencies. "
        "Build specific 30-day calendars, hooks, visuals, CTAs, workflow, and growth decisions."
    )
    answer = call_nvidia_nim_text(
        prompt,
        system_prompt=creator_system_prompt,
        model_id=nim_agent_model(ai_agent, "studio"),
        max_tokens=os.getenv("NVIDIA_NIM_STUDIO_MAX_TOKENS", os.getenv("NVIDIA_NIM_MAX_TOKENS", "3200")),
        timeout=int(os.getenv("NVIDIA_NIM_STUDIO_TIMEOUT", "14")),
    )
    if answer:
        return answer, nim_agent_source(ai_agent, "Creator Copilot")
    answer = call_deepseek_text(
        prompt,
        system_prompt=creator_system_prompt,
        max_tokens=os.getenv("DEEPSEEK_STUDIO_MAX_TOKENS", "3200"),
    )
    if answer:
        return answer, "DeepSeek Creator Copilot"
    answer = call_gemini_text(prompt, api_key=api_key, model_env="GEMINI_TEXT_MODEL", default_model="gemini-2.5-flash")
    if answer:
        return answer, "Gemini Creator Copilot"
    answer = call_groq_text(
        prompt,
        system_prompt="You are Suhana Creator Copilot. Build practical creator operating plans with calendars, hooks, visuals, CTAs, and growth decisions.",
    )
    if answer:
        return answer, "Groq Creator Copilot"
    answer = call_pollinations_text(prompt)
    if answer:
        return answer, "Pollinations Creator Copilot"
    return fallback_creator_plan(niche, audience, tone, goal, brand_colors, brand_voice), nim_agent_source(ai_agent, "Creator Copilot")


def fallback_workflow_package(topic, goal, content_format, brand_summary):
    return f"""# AI Workflow Package

## Campaign Brief
- Topic: {topic}
- Goal: {goal or "Grow audience and generate leads"}
- Format: {content_format or "Reel campaign"}

## Brand Memory Used
{brand_summary}

## Script Direction
Hook: Stop guessing about {topic}. Use this simple framework today.

Body:
1. Name the problem in one clear sentence.
2. Show the mistake most beginners make.
3. Give a 3-step practical fix.
4. Show the result or transformation.
5. End with one action: save, comment, DM, or try it today.

## Image Prompt
Premium high-contrast creator visual for {topic}, clean composition, brand colors from memory, cinematic lighting, social media ready, no clutter.

## Voiceover Direction
Confident, warm, fast enough for short-form video, with pauses after the hook and before the CTA.

## Reel Assembly
- Scene 1: Big hook text with motion.
- Scene 2: Problem demonstration.
- Scene 3: Three-step framework.
- Scene 4: Visual proof or example.
- Scene 5: CTA and brand lockup.

## Caption
{topic} becomes easier when you turn it into one repeatable system. Save this and use it in your next post.

## Next Actions
1. Send the script to Reel Generator.
2. Generate 2 visual variations.
3. Export one 9:16 reel and one 16:9 version.
4. Track saves, comments, completion rate, and profile clicks.
"""


def generate_workflow_package(topic, goal, content_format, brand_summary, api_key=None, ai_agent="auto"):
    prompt = f"""
You are Suhana AI Workflow Builder. Build a practical creator workflow that chains:
Idea -> Script -> Image Prompt -> Voiceover Direction -> Reel Assembly -> Caption -> Performance Tracking.

Topic: {topic}
Goal: {goal or "Grow audience and generate leads"}
Preferred format: {content_format or "Short-form reel"}

Saved brand memory:
{brand_summary}

Rules:
- Use Markdown.
- Make it ready for a creator to execute today.
- Include a strong hook, script outline, exact image prompt, voiceover direction, reel scene plan, caption, hashtags, and metrics.
- Include a section titled exactly "## Image Prompt".
- Keep it premium, simple, and high-converting.
"""
    workflow_system_prompt = (
        "You are Suhana Workflow Builder. Convert one creator idea into a full execution package: "
        "script, image prompt, voice direction, reel plan, captions, hashtags, and tracking."
    )
    answer = call_nvidia_nim_text(
        prompt,
        system_prompt=workflow_system_prompt,
        model_id=nim_agent_model(ai_agent, "studio"),
        max_tokens=os.getenv("NVIDIA_NIM_STUDIO_MAX_TOKENS", os.getenv("NVIDIA_NIM_MAX_TOKENS", "2600")),
        timeout=int(os.getenv("NVIDIA_NIM_STUDIO_TIMEOUT", "14")),
    )
    if answer:
        return answer, nim_agent_source(ai_agent, "Workflow")
    answer = call_deepseek_text(
        prompt,
        system_prompt=workflow_system_prompt,
        max_tokens=os.getenv("DEEPSEEK_STUDIO_MAX_TOKENS", "2600"),
    )
    if answer:
        return answer, "DeepSeek Workflow"
    answer = call_gemini_text(prompt, api_key=api_key)
    if answer:
        return answer, "Gemini Workflow"
    answer = call_groq_text(
        prompt,
        system_prompt="You are Suhana Workflow Builder. Convert one idea into script, image prompt, voice direction, reel plan, caption, and performance workflow.",
    )
    if answer:
        return answer, "Groq Workflow"
    answer = call_pollinations_text(prompt)
    if answer:
        return answer, "Pollinations Workflow"
    return fallback_workflow_package(topic, goal, content_format, brand_summary), nim_agent_source(ai_agent, "Workflow")


def fallback_launch_pack(role, topic, audience, goal, brand_summary):
    role_label = (role or "creator").title()
    audience = audience or "people who need a faster, clearer result"
    goal = goal or "turn the idea into a useful output today"
    return f"""# Suhana Studio Strategy Pack

## 1. User Problem
People interested in **{topic}** do not need more random AI tools. They need one clear path: understand the problem, create the useful output, and know exactly what to do next.

## 2. Target User
| Field | Decision |
|---|---|
| User type | {role_label} |
| Audience | {audience} |
| Goal | {goal} |
| Core job | Move from confusion to a finished, shareable result |

## 3. Positioning
**Suhana AI helps {audience} use {topic} to {goal} without jumping between ten disconnected apps.**

## 4. Best Suhana Workflow
| Step | Tool | What it produces |
|---|---|---|
| 1 | Studio | Strategy, user path, content direction |
| 2 | Brand Memory | Tone, niche, audience, offer, rules |
| 3 | Workflow Builder | Script, visual prompt, voice direction, reel/campaign plan |
| 4 | Tutor / Code / PDF / Reel Tool | The exact utility required by this user |
| 5 | Performance Coach | Improvement plan after publishing or practicing |

## 5. Output Blueprint
- **Promise:** Learn, build, or publish around {topic} with a step-by-step AI workspace.
- **Primary output:** A practical pack the user can act on immediately.
- **Secondary output:** A script, lesson, project plan, or workflow depending on the selected user type.
- **Success metric:** The user finishes one useful thing in the first session.

## 6. High-Retention Script
**Hook:** Most people fail at {topic} because they start with tools instead of a system.

**Scene 1 - Problem:** Show the messy way: notes, tabs, random prompts, half-finished work.

**Scene 2 - Shift:** Say: "Suhana AI turns the idea into a path: learn it, build it, create it, and improve it."

**Scene 3 - Demo:** Type "{topic}" into Studio. Show the workflow map, script/lesson/project plan, and the correct next tool.

**Scene 4 - Result:** Show one finished output: a lesson plan, reel script, debug plan, PDF workflow, or creator campaign.

**CTA:** Start with one problem. Let Suhana choose the workflow, then finish the output.

## 7. Tool Routing
- If the user is a **student**: open AI Tutor, then AI Quiz.
- If the user is an **engineer**: open Suhana Code, then Workflow Builder.
- If the user is a **creator**: open Brand Memory, Creator Copilot, Workflow Builder, then Reel Generator.
- If the user is a **normal user**: open Tools, PDF Editor, Image Editor, or Site Guide.

## 8. Visual Direction
Create a dark premium 4D mind-map interface for **{topic}**. Center node: "Suhana Studio". Branches: Learn, Build, Create, Polish, Grow. Fruits should glow in cyan, mint, violet, pink, gold, and white. Cinematic startup website style, glass UI, no clutter.

## 9. Next Actions
1. Save Brand Memory if this is creator/startup work.
2. Run Workflow Builder for the exact execution pack.
3. Use Tutor, Code, PDF, Image, or Reel tools depending on the route.
4. After output is created, use Performance Coach to improve the next version.
"""


def generate_launch_pack(role, topic, audience, goal, brand_summary, api_key=None, ai_agent="auto"):
    if ai_agent == "fast":
        return fallback_launch_pack(role, topic, audience, goal, brand_summary), "Suhana Instant Launch Engine"
    prompt = f"""
You are Suhana AI Launch Pack, an elite startup product operator.
Create one complete, lovable output pack from one user input.

User type: {role or "creator"}
Topic / idea: {topic}
Audience: {audience or "Not specified"}
Goal: {goal or "Create a useful output that people save, share, and act on"}

Saved brand memory:
{brand_summary}

Rules:
- Use Markdown.
- Make the output feel like a paid startup strategy deliverable, not generic AI text.
- Be extremely structured, specific, and easy for a first-time user to understand.
- Explain which Suhana tool the user should open next and why.
- Include an actual high-retention script with hook, scenes, voiceover, captions, CTA, and visuals.
- Include sections exactly named:
  ## User Problem
  ## Target User
  ## Positioning
  ## Best Suhana Workflow
  ## Output Blueprint
  ## High-Retention Script
  ## Visual Prompt
  ## Tool Routing
  ## Next Best Actions
- If role is student, prioritize lesson, quiz, weak-area report, and revision plan.
- If role is creator, prioritize reel script, visual prompt, caption, hashtags, and content calendar.
- If role is founder, prioritize offer, landing copy, launch post, and acquisition plan.
- If role is developer, prioritize project plan, architecture, tasks, demo script, and portfolio post.
- Include at least two compact Markdown tables.
- Keep it specific to the topic and audience.
- Keep it under 2200 words.
"""
    system_prompt = "You build premium one-click launch packs for creators, students, founders, and developers."
    if api_key:
        answer = call_gemini_text(prompt, api_key=api_key, model_env="GEMINI_TEXT_MODEL", default_model="gemini-2.5-flash-lite")
        if answer:
            return answer, "Gemini Launch Pack"
    answer = call_nvidia_nim_text(
        prompt,
        system_prompt=system_prompt,
        model_id=nim_agent_model(ai_agent, "studio"),
        max_tokens=os.getenv("NVIDIA_NIM_STUDIO_MAX_TOKENS", os.getenv("NVIDIA_NIM_MAX_TOKENS", "3000")),
        timeout=min(6, int(os.getenv("NVIDIA_NIM_STUDIO_TIMEOUT", "14"))),
    )
    if answer:
        return answer, nim_agent_source(ai_agent, "Launch Pack")
    if os.getenv("SUHANA_DEEP_LAUNCH_AI", "0") != "1":
        return fallback_launch_pack(role, topic, audience, goal, brand_summary), "Suhana Instant Launch Engine"
    answer = call_deepseek_text(prompt, system_prompt=system_prompt, max_tokens=os.getenv("DEEPSEEK_STUDIO_MAX_TOKENS", "3000"))
    if answer:
        return answer, "DeepSeek Launch Pack"
    answer = call_gemini_text(prompt, api_key=api_key, model_env="GEMINI_TEXT_MODEL", default_model="gemini-2.5-flash-lite")
    if answer:
        return answer, "Gemini Launch Pack"
    answer = call_groq_text(prompt, system_prompt=system_prompt)
    if answer:
        return answer, "Groq Launch Pack"
    answer = call_pollinations_text(prompt)
    if answer:
        return answer, "Pollinations Launch Pack"
    return fallback_launch_pack(role, topic, audience, goal, brand_summary), nim_agent_source(ai_agent, "Launch Pack")


def mission_tasks_for_role(role, goal):
    role_l = (role or "").lower()
    base = [
        {"id": "mission-brief", "title": "Clarify Mission Brief", "tool": "Mission Mode", "href": "/mission", "why": "Lock the user problem, outcome, audience, and success metric."},
        {"id": "memory", "title": "Save Memory", "tool": "Brand Memory", "href": "/brand-memory", "why": "Make every output personalized and consistent."},
    ]
    if "student" in role_l:
        base += [
            {"id": "lesson", "title": "Learn Weak Topics", "tool": "AI Tutor", "href": "/ai-tutor", "why": "Convert confusion into a simple lesson with examples."},
            {"id": "quiz", "title": "Take Diagnostic Quiz", "tool": "AI Quiz", "href": "/ai-quiz", "why": "Find weak areas and prove progress."},
            {"id": "notes", "title": "Export Revision Notes", "tool": "Tutor PDF Export", "href": "/ai-tutor", "why": "Create a study artifact the user can revise offline."},
        ]
    elif "engineer" in role_l or "developer" in role_l or "code" in role_l:
        base += [
            {"id": "architecture", "title": "Build Project Plan", "tool": "Workflow Builder", "href": "/workflow-builder", "why": "Create architecture, tasks, demo, and build path."},
            {"id": "code", "title": "Solve / Debug Core Code", "tool": "Suhana Code", "href": "/suhana-code", "why": "Generate implementation, edge cases, tests, and review."},
            {"id": "portfolio", "title": "Create Portfolio Story", "tool": "Studio", "href": "/studio", "why": "Turn the build into a resume/demo post."},
        ]
    elif "founder" in role_l or "startup" in role_l or "business" in role_l:
        base += [
            {"id": "positioning", "title": "Position Offer", "tool": "Studio", "href": "/studio", "why": "Define pain, ICP, promise, and wedge."},
            {"id": "launch-content", "title": "Create Launch Content", "tool": "Workflow Builder", "href": "/workflow-builder", "why": "Generate landing copy, launch post, reel script, and CTA."},
            {"id": "performance", "title": "Analyze Market Response", "tool": "Performance Coach", "href": "/performance-coach", "why": "Turn user signals into next experiments."},
        ]
    elif "creator" in role_l:
        base += [
            {"id": "calendar", "title": "Plan 30-Day Content", "tool": "Creator Copilot", "href": "/creator-copilot", "why": "Build repeatable content cadence."},
            {"id": "workflow", "title": "Generate Content Pack", "tool": "Workflow Builder", "href": "/workflow-builder", "why": "Create script, visual prompt, voice direction, caption, and metrics."},
            {"id": "reel", "title": "Produce Reel", "tool": "Create Reel", "href": "/create", "why": "Turn the plan into an export-ready video."},
        ]
    else:
        base += [
            {"id": "workflow", "title": "Build Execution Workflow", "tool": "Workflow Builder", "href": "/workflow-builder", "why": "Turn the goal into ordered action and outputs."},
            {"id": "documents", "title": "Polish Documents / Assets", "tool": "PDF + Image Tools", "href": "/tools", "why": "Clean the output into something usable."},
            {"id": "guide", "title": "Ask Site Guide", "tool": "Suhana Guide", "href": "/site-guide", "why": "Route the user to the exact next feature."},
        ]
    base.append({"id": "review", "title": "Review and Improve", "tool": "Dashboard", "href": "/dashboard", "why": "Track what was produced and decide the next action."})
    return base


def fallback_mission_plan(role, goal, audience, timeline, success_metric, brand_summary):
    tasks = mission_tasks_for_role(role, goal)
    task_rows = "\n".join(
        f"| {idx} | {task['title']} | {task['tool']} | {task['why']} |"
        for idx, task in enumerate(tasks, 1)
    )
    return f"""# Suhana Mission OS

## Mission
**Goal:** {goal}

**Audience:** {audience or "People who need a clear, finished result"}

**Timeline:** {timeline or "Start today, finish first useful output within 7 days"}

**Success Metric:** {success_metric or "One completed output the user can use, submit, publish, or share"}

## Why This Can Win
The user does not need another chatbot. They need one command center that routes learning, creation, coding, documents, and publishing into a single path. Suhana Mission Mode makes the app feel like a personal execution partner.

## Execution Map
| Step | Action | Suhana Tool | Reason |
|---|---|---|---|
{task_rows}

## First Session Experience
1. User enters one real goal.
2. Suhana creates this mission board.
3. User completes the first task immediately.
4. Suhana saves outputs and recommends the next tool.
5. Dashboard shows live work done and progress.

## Output Pack To Create
- Mission brief
- Personalized task rail
- Tool routing
- First script / lesson / project / document path
- Exportable PDF report
- Progress tracking

## Retention Loop
Every completed task should create a saved artifact. The next screen should always answer: "What should I do next?"

## Brand / Memory Context
{brand_summary or "No saved memory yet. Ask the user to save their role, audience, voice, and goal after mission creation."}
"""


def generate_mission_plan(role, goal, audience, timeline, success_metric, brand_summary, previous_context="", api_key=None, ai_agent="auto"):
    prompt = f"""
You are Suhana Mission OS, a world-class AI product operator.
Create a mission workspace plan that turns one user goal into a guided execution system.

User role: {role}
Goal: {goal}
Audience: {audience or "Not specified"}
Timeline: {timeline or "Not specified"}
Success metric: {success_metric or "Not specified"}
Saved memory:
{brand_summary}

Previous Suhana context to continue from:
{previous_context or "No previous context selected."}

Return Markdown only with these sections:
# Suhana Mission OS
## Mission
## Billion-Dollar User Problem
## Execution Map
## First Session Experience
## Tool Routing
## Output Pack To Create
## Retention Loop
## Viral / Sharing Loop
## Next 3 Actions

Rules:
- Be specific to the goal.
- Make it understandable for a first-time user.
- Mention exact Suhana tools: Studio, AI Tutor, AI Quiz, Suhana Code, Creator Copilot, Workflow Builder, Create Reel, PDF Editor, Image Editor, Performance Coach, Dashboard.
- Include one Markdown table.
- Keep under 1500 words.
"""
    system_prompt = "You create execution workspaces, not generic advice. Be structured, practical, and product-grade."
    answer = call_nvidia_nim_text(
        prompt,
        system_prompt=system_prompt,
        model_id=nim_agent_model(ai_agent, "mission"),
        max_tokens=os.getenv("NVIDIA_NIM_MISSION_MAX_TOKENS", "2200"),
        timeout=int(os.getenv("NVIDIA_NIM_MISSION_TIMEOUT", "10")),
    )
    if answer:
        return answer, nim_agent_source(ai_agent, "Mission")
    answer = call_deepseek_text(prompt, system_prompt=system_prompt, max_tokens=os.getenv("DEEPSEEK_MISSION_MAX_TOKENS", "2200"))
    if answer:
        return answer, "DeepSeek Mission"
    answer = call_gemini_text(prompt, api_key=api_key, model_env="GEMINI_MISSION_MODEL", default_model="gemini-2.5-flash")
    if answer:
        return answer, "Gemini Mission"
    answer = call_groq_text(prompt, system_prompt=system_prompt)
    if answer:
        return answer, "Groq Mission"
    answer = call_pollinations_text(prompt)
    if answer:
        return answer, "Pollinations Mission"
    fallback = fallback_mission_plan(role, goal, audience, timeline, success_metric, brand_summary)
    if previous_context:
        fallback += f"\n\n## Loaded Previous Context\n{previous_context[:1800]}\n"
    return fallback, "Suhana Mission Engine"


def mission_history_items(user, limit=18):
    if not user:
        return []
    items = []
    for mission_obj in Mission.query.filter_by(user_id=user.id).order_by(Mission.id.desc()).limit(5).all():
        items.append({
            "key": f"mission:{mission_obj.id}",
            "label": f"Mission - {mission_obj.title[:70]}",
            "kind": "Mission",
            "body": mission_obj.plan_body,
        })
    for run in WorkflowRun.query.filter_by(user_id=user.id).order_by(WorkflowRun.id.desc()).limit(5).all():
        items.append({
            "key": f"workflow:{run.id}",
            "label": f"Workflow - {run.title[:70]}",
            "kind": "Workflow",
            "body": run.output_body,
        })
    for plan in CreatorPlan.query.filter_by(user_id=user.id).order_by(CreatorPlan.id.desc()).limit(4).all():
        items.append({
            "key": f"plan:{plan.id}",
            "label": f"Creator plan - {plan.niche[:70]}",
            "kind": "Creator Plan",
            "body": plan.plan_body,
        })
    for script in Script.query.filter_by(user_id=user.id).order_by(Script.id.desc()).limit(4).all():
        items.append({
            "key": f"script:{script.id}",
            "label": f"Script - {script.topic[:70]}",
            "kind": "Script",
            "body": f"Hook: {script.hook}\n\nScript:\n{script.script_body}\n\nScene plan:\n{script.scene_plan}\n\nCaption:\n{script.caption}",
        })
    return items[:limit]


def selected_history_context(history_items, selected_key):
    for item in history_items:
        if item["key"] == selected_key:
            return f"Loaded from {item['label']}:\n{item['body'][:2600]}"
    return ""


def fallback_startup_analysis(target, audience, goal, context):
    return f"""# Startup / Website Analysis

## What People Want
Users do not want many tools. They want one clear result:

**Tell the app a goal, get a useful output, and know the next step.**

For **{target}**, the strongest product promise should be:

> Start with one goal. Suhana turns it into a plan, content, learning, code, documents, and progress tracking.

## Current Risk
| Problem | Why users leave | Fix |
|---|---|---|
| Too many pages | New users do not know where to start | Make Mission Mode the main start |
| Technical labels | Words like workflow/brand memory feel unclear | Use normal words: plan, steps, saved style, next action |
| Output hidden after generation | User thinks nothing happened | Redirect to board/result immediately |
| Features feel separate | User has to connect tools manually | Add one integrated path from goal to output |

## Best Integrated Environment
1. **Mission Mode:** user writes goal.
2. **Plan:** Suhana creates simple steps.
3. **Do:** each step opens the exact useful tool.
4. **Save:** every output goes to dashboard.
5. **Improve:** quiz/performance/progress analysis tells the next action.

## What To Build Next
- Make Mission Mode the default homepage CTA.
- Add previous-work loading everywhere important.
- Make quiz analysis show weak points, strong points, and next revision.
- Add result history to Tutor and Code, not just scripts/workflows.
- Add one “Continue” button after every output.

## Founder Verdict
This can become a strong startup if it stops selling “AI tools” and sells **finished progress**:

**Study better, build faster, create content, fix documents, and track progress from one goal.**

## Next 7-Day Build Plan
| Day | Build | Why |
|---|---|---|
| 1 | Make Mission Mode simple and primary | Reduces confusion |
| 2 | Add previous chat/work loading | Makes it feel continuous |
| 3 | Improve Quiz analysis | Students see value immediately |
| 4 | Add Continue buttons after outputs | Creates retention |
| 5 | Simplify Studio wording | Removes startup jargon |
| 6 | Add dashboard “today’s next step” | Gives reason to return |
| 7 | Record demo flows | Helps launch and marketing |
"""


def generate_startup_analysis(target, audience, goal, context, api_key=None, ai_agent="auto"):
    prompt = f"""
You are a brutally practical startup product analyst.
Analyze this startup / website / app idea and make it something users actually want.

Target website/startup/app:
{target}

Audience:
{audience or "General users"}

Goal:
{goal or "Make it useful, lovable, and monetizable"}

Extra context:
{context or "No extra context"}

Return Markdown with:
# Startup / Website Analysis
## What People Want
## What Is Confusing
## Missing Killer Feature
## Integrated Environment
## Simplified User Flow
## Features To Remove
## Features To Add
## Monetization
## Next 7-Day Build Plan

Rules:
- Be clear enough for a non-technical founder.
- Avoid buzzwords.
- Focus on what will make users come back.
- Include one table.
- Mention how Suhana AI should connect Mission, Tutor, Quiz, Code, Reels, PDF, Image, Dashboard.
"""
    system_prompt = "You are a startup product analyst. Give direct, useful, non-fluffy product advice."
    answer = call_nvidia_nim_text(
        prompt,
        system_prompt=system_prompt,
        model_id=nim_agent_model(ai_agent, "analysis"),
        max_tokens=os.getenv("NVIDIA_NIM_ANALYSIS_MAX_TOKENS", "2200"),
        timeout=int(os.getenv("NVIDIA_NIM_ANALYSIS_TIMEOUT", "10")),
    )
    if answer:
        return answer, nim_agent_source(ai_agent, "Startup Analyzer")
    answer = call_deepseek_text(prompt, system_prompt=system_prompt, max_tokens=os.getenv("DEEPSEEK_ANALYSIS_MAX_TOKENS", "2200"))
    if answer:
        return answer, "DeepSeek Analyzer"
    answer = call_gemini_text(prompt, api_key=api_key, model_env="GEMINI_ANALYSIS_MODEL", default_model="gemini-2.5-flash")
    if answer:
        return answer, "Gemini Analyzer"
    answer = call_groq_text(prompt, system_prompt=system_prompt)
    if answer:
        return answer, "Groq Analyzer"
    return fallback_startup_analysis(target, audience, goal, context), "Suhana Product Analyzer"


def extract_image_prompt_from_workflow(body, topic):
    body = normalize_ai_text(body)
    match = re.search(r"##\s*Image Prompt\s*(.*?)(?:\n##|\Z)", body, flags=re.I | re.S)
    if match:
        text = re.sub(r"^[\-*: ]+", "", match.group(1).strip())
        text = "\n".join(line.strip("- ").strip() for line in text.splitlines() if line.strip())
        if text:
            return text[:1200]
    return f"Premium social media visual for {topic}, clean high-contrast layout, cinematic lighting, brand-consistent colors, creator campaign asset."


def fallback_performance_coach(platform, content_type, metrics, goal, brand_summary):
    return f"""# AI Performance Coach Report

## What The Numbers Suggest
Your {platform or "social"} {content_type or "content"} data shows one clear job: connect the hook, viewer promise, and next action more tightly.

## Brand Memory Used
{brand_summary}

## Diagnosis
- If impressions are low: the topic/packaging is not getting enough initial curiosity.
- If views are good but watch time is low: the first 3 seconds are not specific enough.
- If saves are low: the content is not useful enough to revisit.
- If comments are low: the CTA is too passive or does not invite opinion.
- If profile clicks are low: the offer/benefit is not clear inside the content.

## Next 7 Posts
| Day | Post Type | Hook | Improvement Goal |
|---|---|---|---|
| 1 | Problem reel | "Stop making this mistake..." | Improve 3-second retention |
| 2 | Tutorial | "Use this 3-step method..." | Increase saves |
| 3 | Proof post | "Before vs after..." | Build trust |
| 4 | Myth post | "Everyone says this, but..." | Increase comments |
| 5 | Checklist | "Save this before you start..." | Increase saves |
| 6 | Story post | "I learned this the hard way..." | Humanize brand |
| 7 | Offer reel | "Want this done faster?" | Increase profile clicks |

## Hook Rewrite System
1. Start with the pain.
2. Add a measurable promise.
3. Make it specific to the audience.
4. Remove generic words.

## Publish Pack
| Platform | Upload Copy |
|---|---|
| YouTube Shorts | Title: "Stop Missing This Simple Content Fix" Description: "Use this 3-step creator system before your next short." |
| Instagram Reels | Caption: "Your next reel needs a clearer promise, stronger first frame, and one direct CTA. Save this before posting." |
| X | "Most creators do not need more tools. They need a repeatable idea to post workflow. Here is the simple version..." |

## Direct Publishing Setup
- Connect YouTube Data API OAuth for real Shorts uploads.
- Connect Instagram Graph API through a Meta Business account for Reels publishing.
- Connect X API OAuth for post/thread publishing.
- Until OAuth is approved, use Suhana to prepare the copy and open each official publishing dashboard.

## Next Action In Suhana
- Put Day 1 into Workflow Builder.
- Generate 2 image variations.
- Create one reel.
- After posting, paste the new metrics here again.
"""


def extract_public_post_context(url):
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    platform = "Unknown"
    if "instagram" in host:
        platform = "Instagram"
        content_kind = "Reel/post"
    elif "youtube" in host or "youtu.be" in host:
        platform = "YouTube"
        content_kind = "Short/video"
    elif "linkedin" in host:
        platform = "LinkedIn"
        content_kind = "Post"
    elif "x.com" in host or "twitter" in host:
        platform = "X"
        content_kind = "Post/thread"
    else:
        content_kind = "Public content"
    slug = path.strip("/").split("/")[-1] if path.strip("/") else ""
    return (
        f"Public link detected: {url}\n"
        f"Detected platform: {platform}\n"
        f"Detected content type: {content_kind}\n"
        f"Detected post/reel id or slug: {slug or 'not visible'}\n"
        "Note: Without official platform API access, Suhana cannot read private analytics directly. "
        "Use visible link context plus pasted metrics/notes for analysis. "
        "If the user connects official OAuth later, use provider APIs for exact caption, comments, watch time, and publish status."
    )


def generate_performance_coach(platform, content_type, metrics, goal, brand_summary, content_url="", api_key=None, ai_agent="auto"):
    link_context = extract_public_post_context(content_url)
    prompt = f"""
You are Suhana AI Performance Coach, a growth strategist for creators and startups.
Analyze the user's content performance and prescribe exactly what to create next.

Platform: {platform or "Not specified"}
Content type: {content_type or "Not specified"}
Goal: {goal or "Grow audience and convert viewers"}
Content URL/context:
{link_context or "No URL supplied"}

Brand memory:
{brand_summary}

User metrics / notes:
{metrics}

Output rules:
- Use Markdown.
- Start with a clear diagnosis, not generic motivation.
- Explain likely bottleneck: hook, retention, usefulness, trust, CTA, offer, consistency, or audience mismatch.
- If a URL is supplied, include a "Link Intelligence" section using the detected platform/content id and what can be inferred safely.
- Give a scorecard table.
- Give 7 next posts with exact hooks.
- Give 3 hook rewrites.
- Give a "Publish Pack" containing: YouTube Shorts title + description, Instagram caption + hashtags, X post/thread starter.
- Give a "Direct publishing setup" checklist explaining OAuth is required for true one-click upload.
- Give what to test next and what metric proves success.
- End with exact Suhana tools to use next.
- Keep answer practical and founder-grade.
"""
    coach_system_prompt = (
        "You are Suhana Performance Coach: diagnose creator metrics, infer safe link context, "
        "and prescribe next posts, hooks, tests, and publishing packs."
    )
    answer = call_nvidia_nim_text(
        prompt,
        system_prompt=coach_system_prompt,
        model_id=nim_agent_model(ai_agent, "studio"),
        max_tokens=os.getenv("NVIDIA_NIM_STUDIO_MAX_TOKENS", os.getenv("NVIDIA_NIM_MAX_TOKENS", "2600")),
        timeout=int(os.getenv("NVIDIA_NIM_STUDIO_TIMEOUT", "14")),
    )
    if answer:
        return answer, nim_agent_source(ai_agent, "Performance Coach")
    answer = call_deepseek_text(
        prompt,
        system_prompt=coach_system_prompt,
        max_tokens=os.getenv("DEEPSEEK_STUDIO_MAX_TOKENS", "2600"),
    )
    if answer:
        return answer, "DeepSeek Performance Coach"
    answer = call_gemini_text(prompt, api_key=api_key, model_env="GEMINI_TEXT_MODEL", default_model="gemini-2.5-flash-lite")
    if answer:
        return answer, "Gemini Performance Coach"
    answer = call_groq_text(
        prompt,
        system_prompt="You are Suhana Performance Coach. Diagnose content metrics and prescribe next posts, hooks, tests, and publishing pack.",
    )
    if answer:
        return answer, "Groq Performance Coach"
    answer = call_pollinations_text(prompt)
    if answer:
        return answer, "Pollinations Performance Coach"
    fallback = fallback_performance_coach(platform, content_type, f"{metrics}\n\n{link_context}", goal, brand_summary)
    return fallback, nim_agent_source(ai_agent, "Performance Coach")


def sigmoid(value):
    try:
        return 1 / (1 + pow(2.718281828, -value))
    except OverflowError:
        return 0 if value < 0 else 1


def ml_growth_prediction(title, format_type, hook, audience, goal, metrics, brand_summary):
    text = " ".join([title or "", format_type or "", hook or "", audience or "", goal or "", metrics or ""]).lower()
    words = re.findall(r"[a-zA-Z0-9]+", text)
    word_count = len(words)
    hook_words = re.findall(r"[a-zA-Z0-9]+", (hook or "").lower())
    numbers = len(re.findall(r"\d+", text))
    question = 1 if "?" in (hook or title or "") else 0
    urgency_terms = sum(1 for term in ["now", "today", "stop", "mistake", "before", "secret", "fast", "simple"] if term in text)
    proof_terms = sum(1 for term in ["proof", "result", "case", "before", "after", "data", "tested", "real"] if term in text)
    audience_terms = len(re.findall(r"student|creator|founder|beginner|agency|coach|business|college|btech", text))
    clarity = max(0, 1 - abs(len(hook_words) - 9) / 16)
    specificity = min(1, (numbers + audience_terms + proof_terms) / 6)
    emotional_pull = min(1, urgency_terms / 4)
    utility = min(1, sum(1 for term in ["how", "steps", "checklist", "framework", "template", "guide", "learn"] if term in text) / 3)
    format_bonus = 0.08 if (format_type or "").lower() in {"reel", "short", "carousel"} else 0
    neural_logit = (
        -1.1
        + 1.25 * clarity
        + 1.45 * specificity
        + 1.15 * emotional_pull
        + 1.2 * utility
        + 0.45 * question
        + format_bonus
    )
    score = round(sigmoid(neural_logit) * 100)
    risks = []
    if clarity < .55:
        risks.append("Hook length is not ideal. Aim for 7-12 punchy words.")
    if specificity < .45:
        risks.append("Add specific audience, number, result, or proof.")
    if emotional_pull < .35:
        risks.append("Add urgency or a mistake/pain point.")
    if utility < .35:
        risks.append("Make the value more practical: checklist, framework, steps, or template.")
    if not risks:
        risks.append("Strong concept. Test two hook variations and compare retention.")
    verdict = "High potential" if score >= 72 else ("Promising but needs sharper packaging" if score >= 52 else "Weak packaging; improve hook and specificity before posting")
    return f"""# ML Growth Lab Prediction

## Neural Score
{score}/100 - {verdict}

## Model Signals
| Signal | Score | Meaning |
|---|---:|---|
| Hook clarity | {round(clarity * 100)} | Best hooks are short, clear, and specific |
| Specificity | {round(specificity * 100)} | Audience, numbers, proof, and concrete outcomes |
| Emotional pull | {round(emotional_pull * 100)} | Mistake, urgency, curiosity, or pain |
| Utility value | {round(utility * 100)} | Practical save-worthy usefulness |
| Question pattern | {question * 100} | Questions can improve curiosity when specific |

## Deep-Learning Style Diagnosis
This lightweight neural scoring engine uses weighted signals from high-performing creator content: clarity, specificity, emotional pull, utility, and format fit. It is designed to run locally without heavy TensorFlow/PyTorch installs.

## Biggest Risks
{chr(10).join(f"- {risk}" for risk in risks)}

## Better Hook Variants
1. Stop making this mistake with {title}.
2. The simple {format_type or "content"} framework for {audience or "your audience"}.
3. I tested this {title} idea so you do not waste time.

## Next Action
- If score is below 70: rewrite the hook and run ML Growth Lab again.
- If score is above 70: send it to Workflow Builder.
- After posting: paste metrics into Performance Coach.

## Brand Memory Used
{brand_summary}
""", score


def create_placeholder_asset(prompt, save_path, label="AI Concept"):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    image = Image.new("RGB", (1080, 1920), (8, 8, 28))
    draw = ImageDraw.Draw(image)
    colors = [(125, 211, 252), (52, 211, 153), (196, 181, 253)]

    for index, color in enumerate(colors):
        x = 120 + index * 190
        y = 260 + index * 170
        draw.ellipse((x, y, x + 520, y + 520), outline=color, width=8)

    title = label
    body = (prompt or "AI generated visual concept")[:130]
    draw.text((90, 760), title, fill=(125, 211, 252))
    draw.text((90, 850), body, fill=(240, 240, 255))
    draw.text((90, 1110), "Generated preview asset", fill=(52, 211, 153))
    image.save(save_path)
    return save_path


def normalize_aspect_ratio(value, default="9:16"):
    value = (value or default).strip()
    return value if value in {"9:16", "16:9", "1:1", "4:5"} else default


def image_dimensions_for_aspect(aspect_ratio, provider="pollinations"):
    aspect_ratio = normalize_aspect_ratio(aspect_ratio)
    if provider == "openai":
        return {
            "9:16": "1024x1536",
            "16:9": "1536x1024",
            "1:1": "1024x1024",
            "4:5": "1024x1536",
        }.get(aspect_ratio, "1024x1536")
    return {
        "9:16": (768, 1344),
        "16:9": (1344, 768),
        "1:1": (1024, 1024),
        "4:5": (1024, 1280),
    }.get(aspect_ratio, (768, 1344))


def enhance_visual_prompt(prompt, aspect_ratio="9:16", preferred_model="auto", asset_type="image"):
    aspect_ratio = normalize_aspect_ratio(aspect_ratio)
    model_hint = (preferred_model or "auto").replace("_", " ")
    base = prompt or "premium creator-ready AI visual"
    if asset_type == "video":
        return (
            f"{base}. Create a cinematic {aspect_ratio} video storyboard keyframe set, 5 scene beats, "
            f"camera motion notes, premium lighting, sharp subject, clean composition, model preference {model_hint}."
        )
    return (
        f"{base}. Aspect ratio {aspect_ratio}. Ultra-detailed premium AI image, strong composition, "
        f"clean lighting, realistic texture, creator-ready, no watermark, no text artifacts, model preference {model_hint}."
    )


def generate_openai_image(prompt, save_path, api_key=None, aspect_ratio="9:16"):
    load_dotenv(override=True)
    active_openai_key = (os.getenv("OPENAI_API_KEY") or OPENAI_API_KEY) if api_key is None else api_key

    if not active_openai_key or not OpenAI:
        return None

    try:
        client = OpenAI(api_key=active_openai_key)
        response = client.images.generate(
            model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
            prompt=prompt,
            size=image_dimensions_for_aspect(aspect_ratio, provider="openai"),
        )
        image_base64 = response.data[0].b64_json

        with open(save_path, "wb") as f:
            f.write(base64.b64decode(image_base64))

        return save_path
    except Exception as e:
        print("OpenAI image fallback used:", e)
        return None


def generate_free_image(prompt, save_path, aspect_ratio="9:16", preferred_model=None):
    prompt_text = prompt or "vertical creator-ready social media image"
    enhanced_prompt = enhance_visual_prompt(prompt_text, aspect_ratio=aspect_ratio, preferred_model=preferred_model)
    encoded_prompt = urllib.parse.quote(enhanced_prompt)
    width, height = image_dimensions_for_aspect(aspect_ratio, provider="pollinations")
    params = urllib.parse.urlencode({
        "width": str(width),
        "height": str(height),
        "nologo": "true",
        "enhance": "true",
        "model": preferred_model if preferred_model and preferred_model != "auto" else os.getenv("FREE_IMAGE_MODEL", "flux"),
    })
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?{params}"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SuhanaAI/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=90) as response:
            content_type = response.headers.get("Content-Type", "")
            image_bytes = response.read()

        if "image" not in content_type or len(image_bytes) < 1000:
            print("Free image fallback used: response was not an image")
            return None

        with open(save_path, "wb") as f:
            f.write(image_bytes)
        return save_path
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
        print("Free image fallback used:", e)
        return None


def valid_generated_file(path):
    return bool(path and os.path.exists(path) and os.path.getsize(path) > 1000)


def generate_ai_image_asset(prompt, save_path, user=None, aspect_ratio="9:16", preferred_model="auto", asset_type="image"):
    enhanced_prompt = enhance_visual_prompt(prompt, aspect_ratio=aspect_ratio, preferred_model=preferred_model, asset_type=asset_type)
    order = [
        item.strip().lower()
        for item in os.getenv("IMAGE_PROVIDER_ORDER", "gemini,openai,pollinations,leonardo").split(",")
        if item.strip()
    ]
    if preferred_model in {"gemini", "openai", "pollinations", "leonardo"}:
        order = [preferred_model] + order
    provider_names = {
        "gemini": "Gemini Image",
        "openai": "OpenAI Image",
        "pollinations": "Pollinations Free Image",
        "free": "Pollinations Free Image",
        "leonardo": "Leonardo AI",
    }
    generators = {
        "gemini": lambda: generate_gemini_image(enhanced_prompt, save_path, api_key=gemini_key_for_user(user)),
        "openai": lambda: generate_openai_image(enhanced_prompt, save_path, api_key=openai_key_for_user(user), aspect_ratio=aspect_ratio),
        "pollinations": lambda: generate_free_image(enhanced_prompt, save_path, aspect_ratio=aspect_ratio, preferred_model=preferred_model),
        "free": lambda: generate_free_image(enhanced_prompt, save_path, aspect_ratio=aspect_ratio, preferred_model=preferred_model),
        "leonardo": lambda: generate_leonardo_image(enhanced_prompt, save_path, api_key=leonardo_key_for_user(user)),
    }

    last_error = None
    for provider in unique_items(order):
        generator = generators.get(provider)
        if not generator:
            continue
        try:
            if generator() and valid_generated_file(save_path):
                return provider_names.get(provider, provider.title())
        except Exception as e:
            last_error = e
            print(f"{provider} image provider failed:", e)

    if last_error:
        print("All image providers failed. Last error:", last_error)
    return None


def generate_leonardo_image(prompt, save_path, api_key=None):
    active_leonardo_key = LEONARDO_API_KEY if api_key is None else api_key

    if not active_leonardo_key:
        return None

    base_url = "https://cloud.leonardo.ai/api/rest/v1"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {active_leonardo_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "alchemy": False,
        "height": int(os.getenv("LEONARDO_IMAGE_HEIGHT", "1344")),
        "modelId": os.getenv("LEONARDO_MODEL_ID", "7b592283-e8a7-4c5a-9ba6-d18c31f258b9"),
        "contrast": 3.5,
        "num_images": 1,
        "prompt": prompt or "Create a vertical creator-ready image for a short-form reel.",
        "public": False,
        "width": int(os.getenv("LEONARDO_IMAGE_WIDTH", "768")),
        "ultra": False,
    }

    try:
        create_req = urllib.request.Request(
            f"{base_url}/generations",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(create_req, timeout=60) as response:
            create_data = json.loads(response.read().decode("utf-8"))

        generation_id = (
            create_data.get("sdGenerationJob", {}).get("generationId")
            or create_data.get("generationId")
            or create_data.get("id")
        )
        if not generation_id:
            print("Leonardo image fallback used: no generation id returned")
            return None

        get_headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {active_leonardo_key}",
        }

        for _ in range(int(os.getenv("LEONARDO_POLL_ATTEMPTS", "24"))):
            time.sleep(int(os.getenv("LEONARDO_POLL_SECONDS", "3")))
            get_req = urllib.request.Request(
                f"{base_url}/generations/{generation_id}",
                headers=get_headers,
                method="GET",
            )
            with urllib.request.urlopen(get_req, timeout=60) as response:
                generation_data = json.loads(response.read().decode("utf-8"))

            generation = generation_data.get("generations_by_pk") or generation_data
            status = generation.get("status")
            images = generation.get("generated_images") or []

            if images and images[0].get("url"):
                image_req = urllib.request.Request(images[0]["url"], method="GET")
                with urllib.request.urlopen(image_req, timeout=60) as image_response:
                    image_bytes = image_response.read()
                with open(save_path, "wb") as f:
                    f.write(image_bytes)
                return save_path

            if status in {"FAILED", "ERROR"}:
                print("Leonardo image fallback used: generation failed")
                return None

        print("Leonardo image fallback used: generation timed out")
        return None
    except urllib.error.HTTPError as e:
        try:
            error_body = e.read().decode("utf-8")[:600]
        except Exception:
            error_body = str(e)
        print("Leonardo image fallback used:", error_body)
        return None
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
        print("Leonardo image fallback used:", e)
        return None


def generate_gemini_image(prompt, save_path, api_key=None):
    load_dotenv(override=True)
    active_gemini_key = (os.getenv("GEMINI_API_KEY") or GEMINI_API_KEY) if api_key is None else api_key

    if not active_gemini_key:
        return None

    model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{
            "parts": [{
                "text": prompt or "Create a vertical creator-ready image for a short-form reel."
            }]
        }]
    }

    request_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=request_data,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": active_gemini_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))

        for candidate in data.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                inline_data = part.get("inlineData") or part.get("inline_data")
                if inline_data and inline_data.get("data"):
                    with open(save_path, "wb") as f:
                        f.write(base64.b64decode(inline_data["data"]))
                    return save_path

        print("Gemini image fallback used: no inline image returned")
        return None
    except urllib.error.HTTPError as e:
        try:
            error_body = e.read().decode("utf-8")[:600]
        except Exception:
            error_body = str(e)
        print("Gemini image fallback used:", error_body)
        return None
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
        print("Gemini image fallback used:", e)
        return None


def edit_openai_image(input_path, prompt, save_path, api_key=None):
    load_dotenv(override=True)
    active_openai_key = api_key or os.getenv("OPENAI_API_KEY") or OPENAI_API_KEY

    if not active_openai_key or not OpenAI:
        return None

    try:
        client = OpenAI(api_key=active_openai_key)
        with open(input_path, "rb") as image_file:
            response = client.images.edit(
                model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
                image=image_file,
                prompt=prompt,
                size="1024x1024",
            )

        image_base64 = response.data[0].b64_json
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(image_base64))

        return save_path
    except Exception as e:
        print("OpenAI image edit fallback used:", e)
        return None


def allowed_upload(filename, allowed):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def process_reel_job_now(folder_id):
    if os.getenv("PROCESS_REELS_INLINE", "1") != "1":
        return

    try:
        from worker import process_single_reel

        process_single_reel(folder_id)
    except Exception as e:
        print("Inline reel processing failed:", folder_id, e)


def process_reel_job_async(folder_id):
    def runner():
        try:
            from worker import process_single_reel

            process_single_reel(folder_id)
        except Exception as e:
            print("Async reel processing failed:", folder_id, e)

    threading.Thread(target=runner, daemon=True).start()
 

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    return {"ok": True, "service": "Suhana AI", "time": datetime.utcnow().isoformat() + "Z"}


@app.route("/readiness")
def readiness():
    checks = {
        "database": False,
        "secret_key": bool(FLASK_SECRET_KEY and FLASK_SECRET_KEY != "change_this_to_a_long_random_secret"),
        "gemini_key": bool(GEMINI_API_KEY),
        "elevenlabs_key": bool(os.getenv("ELEVENLABS_API_KEY")),
        "google_oauth": bool(oauth and GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        "encryption_key": bool(ENCRYPTION_KEY),
        "public_base_url": bool(os.getenv("PUBLIC_BASE_URL")),
    }
    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False
    required = {"database", "secret_key", "gemini_key", "elevenlabs_key", "public_base_url"}
    ready = all(checks.get(name) for name in required)
    return {"ready": ready, "checks": checks}, 200 if ready else 503


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, title="Page not found", message="This page does not exist or has moved."), 404


@app.errorhandler(429)
def too_many_requests(_error):
    return render_template("error.html", code=429, title="Too many requests", message="Please wait a few minutes and try again."), 429


@app.errorhandler(500)
def server_error(_error):
    return render_template("error.html", code=500, title="Something went wrong", message="Suhana AI hit a server error. Try again, or check the AI Health page if generation failed."), 500


@app.route("/studio", methods=["GET", "POST"])
def studio():
    user = current_user()
    memory = brand_memory_for_user(user)
    form = {
        "role": request.args.get("role", (user.purpose if user else "") or "creator"),
        "topic": request.args.get("topic", ""),
        "audience": memory.audience if memory and memory.audience else "",
        "goal": (user.primary_goal if user else "") or "create one useful result today",
        "ai_agent": "auto",
    }
    result = None
    result_html = None
    source = None
    latest_runs = WorkflowRun.query.filter_by(user_id=user.id).order_by(WorkflowRun.id.desc()).limit(4).all() if user else []

    if request.method == "POST":
        if not user:
            return redirect(url_for("signup", next="/studio"))
        for key in form:
            form[key] = (request.form.get(key) or form[key]).strip()
        if not form["topic"]:
            result = "Please enter one real problem, topic, product, lesson, or campaign first."
            source = "Validation"
        else:
            result, source = generate_launch_pack(
                form["role"],
                form["topic"],
                form["audience"],
                form["goal"],
                brand_memory_summary(memory),
                api_key=gemini_key_for_user(user),
                ai_agent=form["ai_agent"],
            )
            run = WorkflowRun(
                user_id=user.id,
                title=f"Studio Strategy: {form['topic']}"[:180],
                goal=form["goal"],
                steps=json.dumps(["Problem", "User", "Workflow", "Script", "Routing", "Next action"]),
                output_body=result,
                source=source,
            )
            db.session.add(run)
            db.session.commit()
            latest_runs = WorkflowRun.query.filter_by(user_id=user.id).order_by(WorkflowRun.id.desc()).limit(4).all()
        result_html = render_ai_markdown(result)

    return render_template(
        "studio.html",
        form=form,
        memory=memory,
        result=result,
        result_html=result_html,
        source=source,
        latest_runs=latest_runs,
    )


@app.route("/launch-pack", methods=["GET", "POST"])
def launch_pack():
    return redirect(url_for("studio"))


@app.route("/mission", methods=["GET", "POST"])
def mission():
    user = current_user()
    form = {
        "role": user.purpose if user and user.purpose else "student",
        "goal": user.primary_goal if user and user.primary_goal else "",
        "audience": "",
        "timeline": "7 days",
        "success_metric": "",
        "ai_agent": "auto",
        "history_key": "",
    }
    result = None
    result_html = None
    source = None
    created_mission = None
    missions = []
    history_items = mission_history_items(user)

    if user:
        missions = Mission.query.filter_by(user_id=user.id).order_by(Mission.id.desc()).limit(8).all()

    if request.method == "POST":
        if not user:
            session["pending_mission_goal"] = request.form.get("goal") or ""
            return redirect(url_for("signup", next=url_for("mission")))
        form["role"] = (request.form.get("role") or "student").strip()
        form["goal"] = (request.form.get("goal") or "").strip()
        form["audience"] = (request.form.get("audience") or "").strip()
        form["timeline"] = (request.form.get("timeline") or "").strip()
        form["success_metric"] = (request.form.get("success_metric") or "").strip()
        form["ai_agent"] = (request.form.get("ai_agent") or "auto").strip()
        form["history_key"] = (request.form.get("history_key") or "").strip()
        if not form["goal"]:
            result = "## Add a goal\n\nTell Suhana what you want to achieve. Example: `prepare for DSA interviews in 30 days`."
            source = "Validation"
        else:
            memory = brand_memory_for_user(user)
            brand_summary = brand_memory_summary(memory)
            previous_context = selected_history_context(history_items, form["history_key"])
            result, source = generate_mission_plan(
                form["role"],
                form["goal"],
                form["audience"],
                form["timeline"],
                form["success_metric"],
                brand_summary,
                previous_context,
                api_key=gemini_key_for_user(user),
                ai_agent=form["ai_agent"],
            )
            tasks = mission_tasks_for_role(form["role"], form["goal"])
            progress = {task["id"]: False for task in tasks}
            created_mission = Mission(
                user_id=user.id,
                title=form["goal"][:180],
                role=form["role"],
                goal=form["goal"],
                audience=form["audience"],
                timeline=form["timeline"],
                success_metric=form["success_metric"],
                plan_body=result,
                tasks_json=json.dumps(tasks),
                progress_json=json.dumps(progress),
                source=source,
            )
            db.session.add(created_mission)
            if not user.primary_goal:
                user.primary_goal = form["goal"][:220]
            if not user.purpose:
                user.purpose = form["role"][:80]
            db.session.commit()
            missions = Mission.query.filter_by(user_id=user.id).order_by(Mission.id.desc()).limit(8).all()
            return redirect(url_for("mission_detail", mission_id=created_mission.id))

    pending_goal = session.pop("pending_mission_goal", "")
    if pending_goal and not form["goal"]:
        form["goal"] = pending_goal
    if result:
        result_html = render_ai_markdown(result)

    return render_template(
        "mission.html",
        form=form,
        result=result,
        result_html=result_html,
        source=source,
        missions=missions,
        created_mission=created_mission,
        history_items=history_items,
    )


def mission_for_current_user(mission_id):
    mission_obj = Mission.query.get(mission_id)
    if not mission_obj:
        return None
    if "user_id" not in session or mission_obj.user_id != session["user_id"]:
        return None
    return mission_obj


def save_user_work(user, work_type, title, prompt, output, source, href):
    if not user or not output:
        return None
    item = SavedWork(
        user_id=user.id,
        work_type=(work_type or "Work")[:50],
        title=(title or "Untitled work")[:220],
        prompt=(prompt or "")[:4000],
        output=output,
        source=(source or "")[:80],
        href=(href or "")[:240],
    )
    db.session.add(item)
    db.session.commit()
    return item


@app.route("/saved-work/<int:work_id>")
def saved_work_detail(work_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    item = SavedWork.query.get(work_id)
    if not item or item.user_id != session["user_id"]:
        return redirect(url_for("dashboard"))
    return render_template(
        "saved_work.html",
        item=item,
        output_html=render_ai_markdown(item.output),
    )


@app.route("/mission/<int:mission_id>")
def mission_detail(mission_id):
    mission_obj = mission_for_current_user(mission_id)
    if not mission_obj:
        return redirect(url_for("mission"))
    tasks = json.loads(mission_obj.tasks_json or "[]")
    progress = json.loads(mission_obj.progress_json or "{}")
    completed = sum(1 for task in tasks if progress.get(task.get("id")))
    percent = round((completed / max(len(tasks), 1)) * 100)
    return render_template(
        "mission_detail.html",
        mission=mission_obj,
        tasks=tasks,
        progress=progress,
        completed=completed,
        percent=percent,
        plan_html=render_ai_markdown(mission_obj.plan_body),
    )


@app.route("/mission/<int:mission_id>/toggle", methods=["POST"])
def mission_toggle(mission_id):
    mission_obj = mission_for_current_user(mission_id)
    if not mission_obj:
        return redirect(url_for("mission"))
    task_id = request.form.get("task_id")
    progress = json.loads(mission_obj.progress_json or "{}")
    if task_id:
        progress[task_id] = not bool(progress.get(task_id))
    mission_obj.progress_json = json.dumps(progress)
    mission_obj.updated_at = datetime.utcnow()
    tasks = json.loads(mission_obj.tasks_json or "[]")
    if tasks and all(progress.get(task.get("id")) for task in tasks):
        mission_obj.status = "completed"
    else:
        mission_obj.status = "active"
    db.session.commit()
    return redirect(url_for("mission_detail", mission_id=mission_obj.id))


@app.route("/mission/<int:mission_id>/export")
def mission_export(mission_id):
    mission_obj = mission_for_current_user(mission_id)
    if not mission_obj:
        return redirect(url_for("mission"))
    tasks = json.loads(mission_obj.tasks_json or "[]")
    progress = json.loads(mission_obj.progress_json or "{}")
    task_lines = "\n".join(
        f"- [{'x' if progress.get(task.get('id')) else ' '}] {task.get('title')} via {task.get('tool')}: {task.get('why')}"
        for task in tasks
    )
    body = f"""Mission: {mission_obj.goal}
Role: {mission_obj.role}
Timeline: {mission_obj.timeline or "Not set"}
Success Metric: {mission_obj.success_metric or "Not set"}

Tasks:
{task_lines}

Plan:
{mission_obj.plan_body}
"""
    os.makedirs(os.path.join("static", "tools"), exist_ok=True)
    output_file = f"mission_{mission_obj.id}_{uuid.uuid4()}.pdf"
    output_path = os.path.join("static", "tools", output_file)
    if not write_text_pdf("Suhana Mission OS", body, output_path):
        return "PDF export failed. Install Pillow and try again.", 500
    return redirect(url_for("static", filename=f"tools/{output_file}"))


@app.route("/startup-analyzer", methods=["GET", "POST"])
def startup_analyzer():
    result = None
    result_html = None
    source = None
    form = {
        "target": "",
        "audience": "",
        "goal": "",
        "context": "",
        "ai_agent": "auto",
    }
    if request.method == "POST":
        form["target"] = (request.form.get("target") or "").strip()
        form["audience"] = (request.form.get("audience") or "").strip()
        form["goal"] = (request.form.get("goal") or "").strip()
        form["context"] = (request.form.get("context") or "").strip()
        form["ai_agent"] = (request.form.get("ai_agent") or "auto").strip()
        if not form["target"]:
            result = "## Add something to analyze\n\nPaste your startup idea, website link, app description, or product flow."
            source = "Validation"
        else:
            result, source = generate_startup_analysis(
                form["target"],
                form["audience"],
                form["goal"],
                form["context"],
                api_key=gemini_key_for_user(current_user()),
                ai_agent=form["ai_agent"],
            )
            result_html = render_ai_markdown(result)
    return render_template("startup_analyzer.html", form=form, result=result, result_html=result_html, source=source)


@app.route("/create", methods=["GET", "POST"])
def create():
    is_guest = "user_id" not in session
    if is_guest and "guest_id" not in session:
        session["guest_id"] = str(uuid.uuid4())

    myid = str(uuid.uuid4())

    if request.method == "POST":
        rec_id = request.form.get("uuid")
        desc = request.form.get("text")
        generation_source = request.form.get("generation_source", "upload")
        visual_prompt = request.form.get("visual_prompt")
        aspect_ratio = normalize_aspect_ratio(request.form.get("aspect_ratio"), "9:16")
        preferred_model = request.form.get("preferred_model", "auto")
        saved_asset_file = request.form.get("saved_asset_file")
        owner_id = session.get("user_id", 0)
        owner_folder = str(owner_id) if not is_guest else f"guest_{session['guest_id']}"
        user = current_user()
        reel_usage_before = usage_count(user, "reel")

        if is_guest and not can_guest_generate("reel"):
            return trial_prompt("reel")
        if user and not can_use_feature(user, "reel"):
            return upgrade_prompt("reel")

        user_upload_dir = os.path.join(
            app.config["UPLOAD_FOLDER"],
            owner_folder,
            rec_id
        )

        os.makedirs(user_upload_dir, exist_ok=True)

        input_files = []
        allowed_media = {"png", "jpg", "jpeg", "webp", "mp4", "mov"}

        for key, file in request.files.items():
            if file and file.filename:
                if not allowed_upload(file.filename, allowed_media):
                    return "Unsupported media type"
                filename = secure_filename(file.filename)

                file.save(os.path.join(user_upload_dir, filename))
                input_files.append(filename)

        if generation_source == "saved_asset" and saved_asset_file and not input_files:
            source_path = os.path.join("static", "tools", secure_filename(saved_asset_file))
            if os.path.exists(source_path):
                filename = secure_filename(saved_asset_file)
                shutil.copy(source_path, os.path.join(user_upload_dir, filename))
                input_files.append(filename)

        if generation_source == "ai_image" and not input_files:
            filename = "ai_generated_image.png"
            save_path = os.path.join(user_upload_dir, filename)
            provider = generate_ai_image_asset(
                visual_prompt or desc,
                save_path,
                user=user,
                aspect_ratio=aspect_ratio,
                preferred_model=preferred_model,
            )
            if not provider:
                create_placeholder_asset(visual_prompt or desc, save_path, label="AI Image Concept")
            input_files.append(filename)

        if generation_source == "ai_video" and not input_files:
            filename = "ai_video_storyboard.png"
            save_path = os.path.join(user_upload_dir, filename)
            provider = generate_ai_image_asset(
                visual_prompt or desc,
                save_path,
                user=user,
                aspect_ratio=aspect_ratio,
                preferred_model=preferred_model,
                asset_type="video",
            )
            if not provider:
                create_placeholder_asset(visual_prompt or desc, save_path, label="AI Video Storyboard")
            input_files.append(filename)

        if not input_files:
            create_placeholder_asset(visual_prompt or desc, os.path.join(user_upload_dir, "fallback_visual.png"), label="Fallback Visual")
            input_files.append("fallback_visual.png")

        with open(os.path.join(user_upload_dir, "desc.txt"), "w", encoding="utf-8") as f:
            f.write(desc or "")
        with open(os.path.join(user_upload_dir, "aspect_ratio.txt"), "w", encoding="utf-8") as f:
            f.write(aspect_ratio)

        with open(os.path.join(user_upload_dir, "input.txt"), "w", encoding="utf-8") as f:
            for fl in input_files:
                f.write(f"file '{fl}'\n")
                f.write("duration 1\n")
            if input_files:
                f.write(f"file '{input_files[-1]}'\n")
        new_reel = Reel(
            user_id=owner_id,
            folder_id=rec_id,
            status="pending"
        )

        db.session.add(new_reel)
        db.session.commit()
        charge_after_free_limit(user, "reel", reel_usage_before)
        record_guest_generation("reel")
        process_reel_job_now(rec_id)
        if os.getenv("PROCESS_REELS_INLINE", "1") != "1":
            process_reel_job_async(rec_id)

        return redirect(url_for("reel_status", folder_id=rec_id))

    prefill_script = session.pop("prefill_script", "")
    prefill_visual_prompt = session.pop("prefill_visual_prompt", "")
    saved_asset_file = session.pop("prefill_asset_file", "")

    return render_template(
        "create.html",
        myid=myid,
        is_guest=is_guest,
        upload_only=True,
        prefill_script=prefill_script,
        prefill_visual_prompt=prefill_visual_prompt,
        saved_asset_file=saved_asset_file,
        voice_provider_configured=bool(os.getenv("ELEVENLABS_API_KEY") or ELEVENLABS_API_KEY),
    )

@app.route("/gallery")
def gallery():
    if "user_id" not in session:
        return redirect(url_for("login"))

    reels = Reel.query.filter_by(
        user_id=session["user_id"],
        status="completed"
    ).all()

    return render_template("gallery.html", reels=reels)


@app.route("/pricing")
def pricing():
    return render_template("pricing.html")

@app.route("/mock-razorpay")
def mock_razorpay():
    plan = (request.args.get("plan") or "pro").lower()
    plans = {
        "starter": {"name": "Starter Credits", "price": "0", "period": "free trial"},
        "pro": {"name": "Pro Creator", "price": "999", "period": "monthly"},
        "business": {"name": "Business Studio", "price": "2999", "period": "monthly"},
    }
    return render_template("mock_razorpay.html", plan=plans.get(plan, plans["pro"]))

@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    next_url = request.args.get("next") or request.form.get("next") or url_for("mission")
    if not str(next_url).startswith("/"):
        next_url = url_for("mission")
    if request.method == "POST":
        name = request.form.get("name")
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password")
        purpose = (request.form.get("purpose") or "creator").strip()[:80]
        primary_goal = (request.form.get("primary_goal") or "").strip()[:220]

        if not name or not email or not password:
            return "Name, email, and password are required", 400

        if len(password) < 8:
            return "Password must be at least 8 characters long", 400

        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            return "Email already registered"

        hashed_password = generate_password_hash(password)

        new_user = User(
            name=name,
            email=email,
            password_hash=hashed_password,
            credits=0,
            purpose=purpose,
            primary_goal=primary_goal,
        )

        db.session.add(new_user)
        db.session.commit()
        grant_welcome_credits_if_needed(new_user)

        ensure_user_environment(new_user)
        session.clear()
        session["user_id"] = new_user.id
        session["user_name"] = new_user.name
        session["user_email"] = new_user.email
        if primary_goal:
            session["pending_mission_goal"] = primary_goal

        return redirect(next_url)

    return render_template("signup.html", next_url=next_url)


@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or request.form.get("next") or url_for("dashboard")
    if not str(next_url).startswith("/"):
        next_url = url_for("dashboard")
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            grant_welcome_credits_if_needed(user)
            ensure_user_environment(user)
            session.clear()
            session["user_id"] = user.id
            session["user_name"] = user.name
            session["user_email"] = user.email
            return redirect(next_url)

        return "Invalid email or password"

    return render_template("login.html", next_url=next_url)


@app.route("/login/google")
def google_login():
    if not oauth or not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return "Google login is not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env, then install Authlib."

    next_url = request.args.get("next") or url_for("dashboard")
    if not str(next_url).startswith("/"):
        next_url = url_for("dashboard")
    session["oauth_next"] = next_url
    if request.args.get("purpose"):
        session["oauth_purpose"] = request.args.get("purpose")[:80]
    if request.args.get("primary_goal"):
        session["oauth_primary_goal"] = request.args.get("primary_goal")[:220]
    redirect_uri = google_redirect_uri()
    return oauth.google.authorize_redirect(redirect_uri)


def google_redirect_uri():
    host = request.host.split(":")[0].lower()

    if host in {"localhost", "127.0.0.1", "::1"}:
        return url_for("google_callback", _external=True, _scheme="http")

    public_base_url = (
        os.getenv("PUBLIC_BASE_URL")
        or os.getenv("RENDER_EXTERNAL_URL")
        or "https://suhana-ai.onrender.com"
    ).rstrip("/")
    return public_base_url + url_for("google_callback")


@app.route("/oauth-debug")
def oauth_debug():
    return {
        "google_configured": bool(oauth and GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        "current_host": request.host,
        "redirect_uri_to_add_in_google_console": google_redirect_uri(),
    }


@app.route("/auth/google/callback")
def google_callback():
    if not oauth or not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return redirect(url_for("login"))

    token = oauth.google.authorize_access_token()
    profile = token.get("userinfo")

    if not profile:
        profile = oauth.google.get("https://openidconnect.googleapis.com/v1/userinfo").json()

    email = profile.get("email")
    name = profile.get("name") or email
    google_id = profile.get("sub")

    if not email:
        return "Google did not return an email address"

    user = User.query.filter_by(email=email).first()

    if not user:
        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(str(uuid.uuid4())),
            google_id=google_id,
            credits=0,
            purpose=session.get("oauth_purpose"),
            primary_goal=session.get("oauth_primary_goal"),
        )
        db.session.add(user)
    else:
        user.google_id = google_id
        if session.get("oauth_purpose") and not user.purpose:
            user.purpose = session.get("oauth_purpose")
        if session.get("oauth_primary_goal") and not user.primary_goal:
            user.primary_goal = session.get("oauth_primary_goal")

    db.session.commit()
    grant_welcome_credits_if_needed(user)

    ensure_user_environment(user)
    next_url = session.get("oauth_next") or url_for("dashboard")
    session.clear()
    session["user_id"] = user.id
    session["user_name"] = user.name
    session["user_email"] = user.email

    return redirect(next_url if str(next_url).startswith("/") else url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    grant_welcome_credits_if_needed(user)
    ensure_user_environment(user)

    reels_count = Reel.query.filter_by(
        user_id=session["user_id"],
        status="completed"
    ).count()
    pending_count = Reel.query.filter(
        Reel.user_id == session["user_id"],
        Reel.status.in_(["pending", "processing"])
    ).count()
    failed_count = Reel.query.filter_by(
        user_id=session["user_id"],
        status="failed"
    ).count()
    api_keys_count = APIKey.query.filter_by(user_id=session["user_id"]).count()
    brand_memory = brand_memory_for_user(user)
    workflow_count = WorkflowRun.query.filter_by(user_id=session["user_id"]).count()
    script_count = Script.query.filter_by(user_id=session["user_id"]).count()
    asset_count = VisualAsset.query.filter_by(user_id=session["user_id"]).count()
    plan_count = CreatorPlan.query.filter_by(user_id=session["user_id"]).count()
    report_count = PerformanceReport.query.filter_by(user_id=session["user_id"]).count()
    ml_count = MLContentPrediction.query.filter_by(user_id=session["user_id"]).count()
    saved_work_count = SavedWork.query.filter_by(user_id=session["user_id"]).count()
    usage = usage_snapshot(user)
    free_remaining = sum(
        max(item["limit"] - item["used"], 0)
        for item in usage.values()
    )
    recent_reels = Reel.query.filter_by(user_id=session["user_id"]).order_by(Reel.id.desc()).limit(5).all()
    recent_workflows = WorkflowRun.query.filter_by(user_id=session["user_id"]).order_by(WorkflowRun.id.desc()).limit(4).all()
    recent_scripts = Script.query.filter_by(user_id=session["user_id"]).order_by(Script.id.desc()).limit(4).all()
    recent_assets = VisualAsset.query.filter_by(user_id=session["user_id"]).order_by(VisualAsset.id.desc()).limit(4).all()
    recent_saved_work = SavedWork.query.filter_by(user_id=session["user_id"]).order_by(SavedWork.id.desc()).limit(5).all()
    live_activity = []
    for item in recent_saved_work:
        live_activity.append({
            "type": item.work_type,
            "title": item.title,
            "meta": item.source or "Saved AI output",
            "href": url_for("saved_work_detail", work_id=item.id),
        })
    for reel in recent_reels:
        live_activity.append({
            "type": "Reel",
            "title": f"Reel {reel.folder_id[:8]}",
            "meta": reel.status.capitalize(),
            "href": url_for("reel_status", folder_id=reel.folder_id),
        })
    for workflow in recent_workflows:
        live_activity.append({
            "type": "Workflow",
            "title": workflow.title,
            "meta": workflow.status.capitalize(),
            "href": url_for("workflow_builder"),
        })
    for script in recent_scripts:
        live_activity.append({
            "type": "Script",
            "title": script.topic,
            "meta": script.generation_source or "AI",
            "href": url_for("script_generator"),
        })
    for asset in recent_assets:
        live_activity.append({
            "type": asset.asset_type.capitalize(),
            "title": asset.prompt[:70],
            "meta": asset.provider or "Asset",
            "href": url_for("static", filename=f"tools/{asset.file_path}"),
        })
    live_activity = live_activity[:8]

    return render_template(
        "dashboard.html",
        user_name=session["user_name"],
        reels_count=reels_count,
        pending_count=pending_count,
        failed_count=failed_count,
        api_keys_count=api_keys_count,
        brand_memory=brand_memory,
        workflow_count=workflow_count,
        script_count=script_count,
        asset_count=asset_count,
        plan_count=plan_count,
        report_count=report_count,
        ml_count=ml_count,
        saved_work_count=saved_work_count,
        generation_mode=user.generation_mode,
        credits=user.credits or 0,
        user_email=user.email,
        usage=usage,
        free_remaining=free_remaining,
        live_activity=live_activity
    )


@app.route("/admin")
@app.route("/admin/overview")
def admin_overview():
    user = current_user()
    if not is_admin_user(user):
        return render_template_string("""
        <!doctype html>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <body style="margin:0;background:#02020c;color:white;font-family:Arial;padding:28px">
          <h1 style="color:#7dd3fc">Admin Overview Locked</h1>
          <p>Login with founder email to see users and feedback:</p>
          <p style="font-size:20px"><b>sheikhayaan408@gmail.com</b></p>
          <a href="/login" style="display:inline-block;background:#7dd3fc;color:#000;padding:14px 20px;border-radius:12px;text-decoration:none;font-weight:900">Sign In</a>
          <a href="/dashboard" style="display:inline-block;color:white;padding:14px 20px;text-decoration:none">Dashboard</a>
        </body>
        """)

    users = User.query.order_by(User.id.desc()).limit(50).all()
    feedback = ExperienceFeedback.query.order_by(ExperienceFeedback.id.desc()).limit(50).all()
    script_feedback = ScriptFeedback.query.order_by(ScriptFeedback.id.desc()).limit(50).all()
    db_path = os.path.abspath(os.path.join(app.instance_path, "suhana_ai.db"))

    return render_template_string("""
    <!doctype html>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <body style="margin:0;background:#02020c;color:white;font-family:Arial;padding:24px">
      <h1 style="color:#7dd3fc">Suhana AI Admin Overview</h1>
      <p>Database: <b>{{ db_path }}</b></p>
      <h2>Signed In Users</h2>
      <div style="overflow:auto"><table style="width:100%;border-collapse:collapse;min-width:700px">
        <tr><th>ID</th><th>Name</th><th>Email</th><th>Mode</th><th>Credits</th></tr>
        {% for u in users %}
        <tr><td>{{ u.id }}</td><td>{{ u.name }}</td><td>{{ u.email }}</td><td>{{ u.generation_mode }}</td><td>{{ u.credits or 0 }}</td></tr>
        {% endfor %}
      </table></div>
      <h2>Experience Feedback</h2>
      <div style="overflow:auto"><table style="width:100%;border-collapse:collapse;min-width:700px">
        <tr><th>ID</th><th>User ID</th><th>Feature</th><th>Rating</th><th>Notes</th><th>Date</th></tr>
        {% for f in feedback %}
        <tr><td>{{ f.id }}</td><td>{{ f.user_id }}</td><td>{{ f.feature }}</td><td>{{ f.rating }}/5</td><td>{{ f.notes or "" }}</td><td>{{ f.created_at }}</td></tr>
        {% endfor %}
      </table></div>
      <h2>Script Feedback</h2>
      <div style="overflow:auto"><table style="width:100%;border-collapse:collapse;min-width:700px">
        <tr><th>ID</th><th>Script ID</th><th>User ID</th><th>Rating</th><th>Notes</th><th>Date</th></tr>
        {% for f in script_feedback %}
        <tr><td>{{ f.id }}</td><td>{{ f.script_id }}</td><td>{{ f.user_id }}</td><td>{{ f.rating }}/5</td><td>{{ f.notes or "" }}</td><td>{{ f.created_at }}</td></tr>
        {% endfor %}
      </table></div>
      <style>
        th,td{padding:10px;border-bottom:1px solid rgba(255,255,255,.15);text-align:left}
        th{color:#7dd3fc}
      </style>
    </body>
    """, users=users, feedback=feedback, script_feedback=script_feedback, db_path=db_path)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/reel-status/<folder_id>")
def reel_status(folder_id):
    reel = Reel.query.filter_by(folder_id=folder_id).first()

    if not reel:
        return "Reel not found"

    if reel.user_id != 0:
        if "user_id" not in session:
            return redirect(url_for("login"))
        if reel.user_id != session["user_id"]:
            return "You do not have access to this reel"

    voice_status = None
    owner_folder = str(reel.user_id)
    folder_path = os.path.join(app.config["UPLOAD_FOLDER"], owner_folder, reel.folder_id)
    if reel.user_id == 0 and not os.path.isdir(folder_path):
        try:
            for candidate in os.listdir(app.config["UPLOAD_FOLDER"]):
                candidate_path = os.path.join(app.config["UPLOAD_FOLDER"], candidate, reel.folder_id)
                if candidate.startswith("guest_") and os.path.isdir(candidate_path):
                    folder_path = candidate_path
                    break
        except OSError:
            pass
    status_path = os.path.join(folder_path, "voice_status.json")
    if os.path.exists(status_path):
        try:
            with open(status_path, encoding="utf-8") as f:
                voice_status = json.load(f)
        except Exception:
            voice_status = None

    return render_template("reel_status.html", reel=reel, voice_status=voice_status)

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])

    if request.method == "POST":
        mode = request.form.get("generation_mode")

        if mode in ["managed", "byok"]:
            user.generation_mode = mode
            db.session.commit()

        return redirect(url_for("settings"))

    return render_template("settings.html", user=user)


@app.route("/api-vault", methods=["GET", "POST"])
def api_vault():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        provider = request.form.get("provider")
        key_value = request.form.get("key_value")

        if provider not in ALLOWED_API_PROVIDERS:
            return "Unsupported API provider", 400

        if provider and key_value:
            existing_key = APIKey.query.filter_by(
                user_id=session["user_id"],
                provider=provider
            ).first()

            encrypted_key = encrypt_secret(key_value)

            if existing_key:
                existing_key.key_value = encrypted_key
            else:
                new_key = APIKey(
                    user_id=session["user_id"],
                    provider=provider,
                    key_value=encrypted_key
                )
                db.session.add(new_key)

            db.session.commit()

        return redirect(url_for("api_vault"))

    keys = APIKey.query.filter_by(user_id=session["user_id"]).all()
    return render_template("api_vault.html", keys=keys)


@app.route("/api-vault/delete/<int:key_id>", methods=["POST"])
def delete_api_key(key_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    api_key = APIKey.query.filter_by(
        id=key_id,
        user_id=session["user_id"]
    ).first()

    if api_key:
        db.session.delete(api_key)
        db.session.commit()

    return redirect(url_for("api_vault"))


@app.route("/tools")
def tools():
    return render_template("tools.html")


def build_external_bridge_prompt(mode, question, context="", target="Gemini"):
    mode = mode or "Tutor"
    target = target or "Gemini"
    system = {
        "Tutor": "You are an elite AI tutor for Indian students from class 6 to BTech.",
        "Code": "You are a senior software engineer, DSA coach, debugger, and architecture mentor.",
        "Script": "You are a viral short-form video strategist and scriptwriter.",
        "Quiz": "You are a serious exam-setter for school, JEE, BTech, DSA, and placement tests.",
        "Studio": "You are a creator growth strategist for YouTube Shorts, Instagram Reels, and X.",
        "Image": "You are a world-class AI image prompt director.",
        "Business": "You are a startup strategist, product operator, and investor-grade analyst.",
    }.get(mode, "You are a precise expert assistant.")
    requirements = {
        "Tutor": "Teach with simple intuition, formulas where needed, one solved example, mistakes, revision notes, and follow-up questions.",
        "Code": "Give intuition, algorithm, clean code, dry run, complexity, edge cases, tests, and follow-up improvements.",
        "Script": "Return hook, script body, scene plan, caption, hashtags, and CTA.",
        "Quiz": "Return questions with 4 options, correct answer, explanation, difficulty, and weak area.",
        "Studio": "Return a practical creator plan: content angle, hooks, workflow, platform copy, and next actions.",
        "Image": "Return a detailed visual prompt with subject, composition, lighting, style, camera, aspect ratio, negative prompt, and variations.",
        "Business": "Return strategy, user persona, monetization, roadmap, risks, metrics, and next execution steps.",
    }.get(mode, "Give a structured, accurate, useful answer.")
    target_rules = {
        "Gemini": "Use clear sections, strong context, and ask for structured Markdown. Gemini handles longer context well.",
        "ChatGPT": "Ask for crisp reasoning, implementation details, and final answer separation. Use explicit output format.",
        "Claude": "Ask for careful analysis, nuanced tradeoffs, and polished writing. Provide context and constraints clearly.",
        "Llama/Groq": "Keep instructions direct and output schema simple. Avoid overly long context.",
        "Copilot": "Provide exact files, language, constraints, expected behavior, and tests. Ask for code first, explanation after.",
        "Image Model": "Use visual nouns, composition, lighting, lens/camera, style references, aspect ratio, and negative prompt.",
    }.get(target, "Use clear role, task, context, constraints, and output format.")
    return f"""# COPY THIS PROMPT INTO {target.upper()}

## ROLE
{system}

## TARGET AI
{target}

## TARGET-SPECIFIC INSTRUCTION
{target_rules}

## USER REQUEST
{question}

## CONTEXT
{context or "None"}

## TASK
Answer the user request with maximum usefulness and accuracy. Do not give generic advice. Produce a finished deliverable that can be used immediately.

## OUTPUT FORMAT
Use this exact structure unless the user request makes it impossible:
1. Problem understood
2. Assumptions
3. Best answer / deliverable
4. Step-by-step execution
5. Examples / code / formulas / table where useful
6. Quality checklist
7. Common mistakes or risks
8. Next actions
9. 3 follow-up prompts

## MODE-SPECIFIC REQUIREMENTS
1. {requirements}
2. If the answer needs a script, include hook, body, scene plan, caption, CTA, and hashtags.
3. If the answer needs code, include clean code, setup, tests, complexity, and edge cases.
4. If the answer needs learning, include intuition, solved example, practice, weak areas, and revision plan.
5. If the answer needs images, include subject, composition, lighting, style, camera/lens, aspect ratio, and negative prompt.

## QUALITY BAR
- Think carefully before answering.
- State assumptions when input is incomplete.
- Prefer concrete examples, tables, code, formulas, or workflows when useful.
- Make the final answer easy to copy, present, or implement.
- If current/latest facts are needed, clearly state what must be verified.
- Keep the output polished enough for a startup product demo.
"""


@app.route("/ai-bridge", methods=["GET", "POST"])
def ai_bridge():
    mode = (request.form.get("mode") or request.args.get("mode") or "Tutor").strip()
    question = (request.form.get("question") or request.args.get("q") or "").strip()
    context = (request.form.get("context") or "").strip()
    provider = (request.form.get("provider") or request.args.get("provider") or "Gemini").strip()
    bridge_prompt = build_external_bridge_prompt(mode, question, context, provider) if question else ""
    return render_template(
        "ai_bridge.html",
        mode=mode,
        question=question,
        context=context,
        provider=provider,
        bridge_prompt=bridge_prompt,
    )


@app.route("/brand-memory", methods=["GET", "POST"])
def brand_memory():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    memory = brand_memory_for_user(user)

    if request.method == "POST":
        if not memory:
            memory = BrandMemory(user_id=user.id)
            db.session.add(memory)

        memory.brand_name = (request.form.get("brand_name") or "").strip()[:160]
        memory.niche = (request.form.get("niche") or "").strip()[:160]
        memory.audience = (request.form.get("audience") or "").strip()[:240]
        memory.colors = (request.form.get("colors") or "").strip()[:180]
        memory.tone = (request.form.get("tone") or "").strip()[:140]
        memory.logo_url = (request.form.get("logo_url") or "").strip()[:255]
        memory.offer = (request.form.get("offer") or "").strip()[:240]
        memory.content_rules = (request.form.get("content_rules") or "").strip()
        memory.updated_at = datetime.utcnow()
        db.session.commit()
        return redirect(url_for("brand_memory"))

    return render_template("brand_memory.html", memory=memory)


@app.route("/workflow-builder", methods=["GET", "POST"])
def workflow_builder():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    memory = brand_memory_for_user(user)
    result = None
    result_html = None
    source = None
    image_file = None
    script = None
    current_run = None
    latest_runs = WorkflowRun.query.filter_by(user_id=user.id).order_by(WorkflowRun.id.desc()).limit(5).all()
    form = {
        "topic": "",
        "goal": "Grow audience and convert viewers into customers",
        "content_format": "Short-form reel",
        "aspect_ratio": "9:16",
        "preferred_model": "auto",
        "make_image": "yes",
        "ai_agent": "auto",
    }

    if request.method == "POST":
        for key in form:
            form[key] = (request.form.get(key) or form[key]).strip()
        brand_summary = brand_memory_summary(memory)
        if not form["topic"]:
            result = "Please enter a topic or campaign idea first."
            source = "Validation"
        else:
            result, source = generate_workflow_package(
                form["topic"],
                form["goal"],
                form["content_format"],
                brand_summary,
                api_key=gemini_key_for_user(user),
                ai_agent=form["ai_agent"],
            )
            hook = f"Stop scrolling if you want to understand {form['topic']} clearly."
            script_body = plain_text_from_markdown(result)[:3000]
            scene_plan = (
                f"1. Hook screen: {form['topic']}\n"
                "2. Show the core problem.\n"
                "3. Explain the framework from the workflow.\n"
                "4. Show one example or proof point.\n"
                "5. End with CTA and brand memory styling."
            )
            caption = f"Use this workflow for {form['topic']}. Save it and build your next post faster."
            hashtags = "#SuhanaAI #CreatorWorkflow #ContentSystem"
            script_source = source
            error_message = None
            script = Script(
                user_id=user.id,
                topic=form["topic"],
                niche=memory.niche if memory and memory.niche else "Creator",
                tone=memory.tone if memory and memory.tone else "Professional",
                duration="60 seconds",
                hook=hook,
                script_body=script_body,
                scene_plan=scene_plan,
                caption=caption,
                hashtags=hashtags,
                generation_source=script_source,
                error_message=error_message,
            )
            db.session.add(script)
            db.session.flush()

            asset_id = None
            if form["make_image"] == "yes":
                os.makedirs(os.path.join("static", "tools"), exist_ok=True)
                image_prompt = extract_image_prompt_from_workflow(result, form["topic"])
                image_file = f"workflow_{uuid.uuid4()}.png"
                output_path = os.path.join("static", "tools", image_file)
                provider = generate_ai_image_asset(
                    image_prompt,
                    output_path,
                    user=user,
                    aspect_ratio=form["aspect_ratio"],
                    preferred_model=form["preferred_model"],
                )
                if not provider:
                    create_placeholder_asset(image_prompt, output_path, label="Workflow Visual")
                    provider = "Fallback"
                asset = VisualAsset(
                    user_id=user.id,
                    asset_type="workflow-image",
                    prompt=image_prompt,
                    file_path=image_file,
                    provider=provider,
                )
                db.session.add(asset)
                db.session.flush()
                asset_id = asset.id

            run = WorkflowRun(
                user_id=user.id,
                title=form["topic"][:180],
                goal=form["goal"],
                steps=json.dumps(["Idea", "Script", "Image", "Voiceover", "Reel", "Caption", "Metrics"]),
                output_body=result,
                script_id=script.id,
                asset_id=asset_id,
                source=source,
            )
            db.session.add(run)
            db.session.commit()
            current_run = run
            result_html = render_ai_markdown(result)
            latest_runs = WorkflowRun.query.filter_by(user_id=user.id).order_by(WorkflowRun.id.desc()).limit(5).all()

    return render_template(
        "workflow_builder.html",
        memory=memory,
        form=form,
        result=result,
        result_html=result_html,
        source=source,
        image_file=image_file,
        script=script,
        current_run=current_run,
        latest_runs=latest_runs,
    )


@app.route("/creator-copilot", methods=["GET", "POST"])
def creator_copilot():
    user = current_user()
    memory = brand_memory_for_user(user)
    form = {
        "niche": memory.niche if memory and memory.niche else "",
        "audience": memory.audience if memory and memory.audience else "",
        "tone": memory.tone if memory and memory.tone else "Premium but simple",
        "goal": "Grow audience and convert viewers into customers",
        "brand_colors": memory.colors if memory and memory.colors else "",
        "brand_voice": memory.content_rules if memory and memory.content_rules else "",
        "ai_agent": "auto",
    }
    result = None
    result_html = None
    source = None
    current_plan = None
    recent_plans = []

    if request.method == "POST":
        for key in form:
            form[key] = (request.form.get(key) or form[key]).strip()
        if not form["niche"]:
            result = "Please enter a niche first."
            source = "Validation"
        else:
            result, source = generate_creator_copilot_plan(
                form["niche"],
                form["audience"],
                form["tone"],
                form["goal"],
                form["brand_colors"],
                form["brand_voice"],
                api_key=gemini_key_for_user(user),
                ai_agent=form["ai_agent"],
            )
            plan = CreatorPlan(
                user_id=session.get("user_id", 0),
                niche=form["niche"],
                audience=form["audience"],
                tone=form["tone"],
                goal=form["goal"],
                brand_colors=form["brand_colors"],
                brand_voice=form["brand_voice"],
                plan_body=result,
                source=source,
            )
            db.session.add(plan)
            db.session.commit()
            current_plan = plan
        result_html = render_ai_markdown(result) if result else None

    if "user_id" in session:
        recent_plans = CreatorPlan.query.filter_by(user_id=session["user_id"]).order_by(CreatorPlan.id.desc()).limit(4).all()

    return render_template(
        "creator_copilot.html",
        form=form,
        result=result,
        result_html=result_html,
        source=source,
        current_plan=current_plan,
        recent_plans=recent_plans,
    )


@app.route("/performance-coach", methods=["GET", "POST"])
def performance_coach():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    memory = brand_memory_for_user(user)
    result = None
    result_html = None
    source = None
    current_report = None
    reports = PerformanceReport.query.filter_by(user_id=user.id).order_by(PerformanceReport.id.desc()).limit(5).all()
    form = {
        "platform": "Instagram",
        "content_type": "Reel",
        "goal": "Grow audience and convert viewers into customers",
        "content_url": "",
        "metrics": "",
        "ai_agent": "auto",
    }

    if request.method == "POST":
        for key in form:
            form[key] = (request.form.get(key) or form[key]).strip()
        if not form["metrics"]:
            result = "Paste your post metrics or performance notes first."
            source = "Validation"
        else:
            result, source = generate_performance_coach(
                form["platform"],
                form["content_type"],
                form["metrics"],
                form["goal"],
                brand_memory_summary(memory),
                content_url=form["content_url"],
                api_key=gemini_key_for_user(user),
                ai_agent=form["ai_agent"],
            )
            current_report = PerformanceReport(
                user_id=user.id,
                platform=form["platform"],
                content_type=form["content_type"],
                content_url=form["content_url"],
                metrics=form["metrics"],
                goal=form["goal"],
                analysis_body=result,
                source=source,
            )
            db.session.add(current_report)
            db.session.commit()
            reports = PerformanceReport.query.filter_by(user_id=user.id).order_by(PerformanceReport.id.desc()).limit(5).all()
            result_html = render_ai_markdown(result)

    return render_template(
        "performance_coach.html",
        form=form,
        result=result,
        result_html=result_html,
        source=source,
        current_report=current_report,
        reports=reports,
        memory=memory,
    )


@app.route("/ml-growth-lab", methods=["GET", "POST"])
def ml_growth_lab():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    memory = brand_memory_for_user(user)
    result = None
    result_html = None
    score = None
    recent = MLContentPrediction.query.filter_by(user_id=user.id).order_by(MLContentPrediction.id.desc()).limit(5).all()
    form = {
        "title": "",
        "format_type": "Reel",
        "hook": "",
        "audience": memory.audience if memory and memory.audience else "",
        "goal": "Increase saves, shares, and leads",
        "metrics": "",
    }

    if request.method == "POST":
        for key in form:
            form[key] = (request.form.get(key) or form[key]).strip()
        if not form["title"] and not form["hook"]:
            result = "Enter at least a content idea or hook first."
            score = 0
        else:
            result, score = ml_growth_prediction(
                form["title"],
                form["format_type"],
                form["hook"],
                form["audience"],
                form["goal"],
                form["metrics"],
                brand_memory_summary(memory),
            )
            pred = MLContentPrediction(
                user_id=user.id,
                title=(form["title"] or form["hook"])[:180],
                format_type=form["format_type"],
                hook=form["hook"],
                audience=form["audience"],
                prediction_body=result,
                score=score,
            )
            db.session.add(pred)
            db.session.commit()
            recent = MLContentPrediction.query.filter_by(user_id=user.id).order_by(MLContentPrediction.id.desc()).limit(5).all()
        result_html = render_ai_markdown(result)

    return render_template(
        "ml_growth_lab.html",
        form=form,
        result=result,
        result_html=result_html,
        score=score,
        recent=recent,
        memory=memory,
    )


@app.route("/startup-os")
def startup_os():
    return render_template("startup_os.html")


@app.route("/creator-copilot/export/<int:plan_id>")
def export_creator_plan(plan_id):
    plan = CreatorPlan.query.get(plan_id)
    if not plan:
        return "Plan not found", 404
    if plan.user_id != 0 and ("user_id" not in session or plan.user_id != session["user_id"]):
        return redirect(url_for("login"))
    os.makedirs(os.path.join("static", "tools"), exist_ok=True)
    output_file = f"creator_plan_{plan.id}.pdf"
    output_path = os.path.join("static", "tools", output_file)
    if not write_text_pdf(f"Creator Copilot Plan - {plan.niche}", plan.plan_body, output_path):
        return "PDF export failed. Install Pillow and try again.", 500
    return redirect(url_for("static", filename=f"tools/{output_file}"))


@app.route("/workflow-builder/export/<int:run_id>")
def export_workflow_run(run_id):
    run = WorkflowRun.query.get(run_id)
    if not run:
        return "Workflow not found", 404
    if run.user_id != 0 and ("user_id" not in session or run.user_id != session["user_id"]):
        return redirect(url_for("login"))
    os.makedirs(os.path.join("static", "tools"), exist_ok=True)
    output_file = f"workflow_{run.id}.pdf"
    output_path = os.path.join("static", "tools", output_file)
    if not write_text_pdf(f"AI Workflow - {run.title}", run.output_body, output_path):
        return "PDF export failed. Install Pillow and try again.", 500
    return redirect(url_for("static", filename=f"tools/{output_file}"))


@app.route("/ai-health")
def ai_health():
    return render_template("ai_health.html", checks=ai_provider_health())


@app.route("/games")
def games():
    return render_template("games.html")


@app.route("/avatar-maker", methods=["GET", "POST"])
def avatar_maker():
    output_file = None
    name = ""
    style = "Founder"
    if request.method == "POST":
        name = (request.form.get("name") or "Suhana User").strip()
        style = (request.form.get("style") or "Founder").strip()
        try:
            from PIL import Image, ImageDraw, ImageFont
            os.makedirs(os.path.join("static", "tools"), exist_ok=True)
            output_file = f"avatar_{uuid.uuid4()}.png"
            output_path = os.path.join("static", "tools", output_file)
            avatar_prompt = (
                f"Premium futuristic profile avatar for {name}, {style} style, polished founder portrait, "
                "clean face, expressive eyes, cinematic cyan emerald lighting, dark premium AI studio background, "
                "high-end tech brand aesthetic, centered composition, no text, no watermark."
            )
            provider = generate_ai_image_asset(
                avatar_prompt,
                output_path,
                user=current_user(),
                aspect_ratio="1:1",
                preferred_model="auto",
                asset_type="image",
            )
            if provider and valid_generated_file(output_path):
                return render_template("avatar_maker.html", output_file=output_file, name=name, style=style, provider=provider)
            img = Image.new("RGB", (900, 900), (5, 8, 24))
            draw = ImageDraw.Draw(img)
            colors = [(125, 211, 252), (52, 211, 153), (196, 181, 253)]
            for i in range(90):
                r = 620 - i * 5
                col = colors[i % len(colors)]
                draw.ellipse((450-r//2, 450-r//2, 450+r//2, 450+r//2), outline=col, width=2)
            draw.rounded_rectangle((150, 130, 750, 790), radius=72, fill=(7, 13, 32), outline=(52, 211, 153), width=4)
            draw.ellipse((245, 145, 655, 555), fill=(15, 23, 42), outline=(125, 211, 252), width=9)
            draw.polygon([(450, 172), (632, 290), (592, 502), (450, 570), (308, 502), (268, 290)], outline=(196, 181, 253), fill=(10, 18, 38))
            draw.ellipse((330, 265, 390, 325), fill=(125, 211, 252))
            draw.ellipse((510, 265, 570, 325), fill=(52, 211, 153))
            draw.arc((340, 338, 560, 466), 15, 165, fill=(255, 255, 255), width=8)
            draw.rounded_rectangle((190, 610, 710, 790), radius=55, fill=(10, 18, 38), outline=(196, 181, 253), width=5)
            initials = "".join(part[:1] for part in name.split()[:2]).upper() or "AI"
            draw.text((450, 676), initials, fill=(255, 255, 255), anchor="mm")
            draw.text((450, 735), name[:24], fill=(52, 211, 153), anchor="mm")
            draw.text((450, 830), f"{style} Avatar", fill=(125, 211, 252), anchor="mm")
            img.save(output_path)
        except Exception as e:
            print("Avatar maker failed:", e)
    return render_template("avatar_maker.html", output_file=output_file, name=name, style=style, provider="Suhana Local Avatar")


@app.route("/ai-quiz", methods=["GET", "POST"])
def ai_quiz():
    state = "setup"
    questions = []
    analysis = None
    source = None
    topic = ""
    level = "Class 10"
    quiz_type = "Exam practice"
    count = 10
    ai_agent = "auto"
    if request.method == "POST":
        action = request.form.get("action", "generate")
        topic = (request.form.get("topic") or "General aptitude").strip()
        level = (request.form.get("level") or "Class 10").strip()
        quiz_type = (request.form.get("quiz_type") or "Exam practice").strip()
        count = max(3, min(30, int(request.form.get("count", 10) or 10)))
        ai_agent = (request.form.get("ai_agent") or "auto").strip()
        if action == "submit":
            questions = json.loads(request.form.get("questions_json") or "[]")
            answers = {k.replace("answer_", ""): v for k, v in request.form.items() if k.startswith("answer_")}
            analysis = analyze_quiz_result(questions, answers)
            state = "result"
        else:
            questions, source = generate_quiz_questions(topic, level, count, quiz_type, api_key=gemini_key_for_user(current_user()), ai_agent=ai_agent)
            state = "test"
    return render_template(
        "ai_quiz.html",
        state=state,
        questions=questions,
        questions_json=json.dumps(questions),
        analysis=analysis,
        source=source,
        topic=topic,
        level=level,
        quiz_type=quiz_type,
        count=count,
        ai_agent=ai_agent,
    )


@app.route("/quiz-export-pdf", methods=["POST"])
def quiz_export_pdf():
    content = request.form.get("content") or "No quiz result content supplied."
    os.makedirs(os.path.join("static", "tools"), exist_ok=True)
    output_file = f"quiz_result_{uuid.uuid4()}.pdf"
    output_path = os.path.join("static", "tools", output_file)
    if not write_text_pdf("Suhana AI Quiz Result", content, output_path):
        return "PDF export failed. Install Pillow and try again.", 500
    return redirect(url_for("static", filename=f"tools/{output_file}"))


@app.route("/site-guide", methods=["GET", "POST"])
def site_guide():
    result = None
    source = None
    question = ""
    if request.method == "POST":
        question = (request.form.get("question") or "").strip()
        if question:
            result, source = generate_site_guide_answer(
                question,
                api_key=gemini_key_for_user(current_user()),
            )
        else:
            result = "Ask anything about Suhana AI tools, credits, login, image generation, reels, tutor, coding, or PDF editor."
            source = "Validation"
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return {
                "answer": result,
                "answer_html": str(render_ai_markdown(result)),
                "source": source,
            }
    return render_template(
        "site_guide.html",
        result=result,
        result_html=render_ai_markdown(result) if result else None,
        source=source,
        question=question,
    )


@app.route("/ai-tutor", methods=["GET", "POST"])
def ai_tutor():
    result = None
    source = None
    user = current_user()
    recent_tutor_work = SavedWork.query.filter_by(user_id=user.id, work_type="Tutor").order_by(SavedWork.id.desc()).limit(5).all() if user else []
    form = {
        "subject": "",
        "topic": "",
        "level": "Class 10",
        "style": "Simple and practical",
        "resources": "",
        "follow_up": "",
        "ai_agent": "auto",
    }

    if request.method == "POST":
        form["subject"] = (request.form.get("subject") or "").strip()
        form["topic"] = (request.form.get("topic") or "").strip()
        form["level"] = (request.form.get("level") or "").strip()
        form["style"] = (request.form.get("style") or "").strip()
        form["resources"] = (request.form.get("resources") or "").strip()
        form["follow_up"] = (request.form.get("follow_up") or "").strip()
        form["ai_agent"] = (request.form.get("ai_agent") or "auto").strip()
        previous_answer = (request.form.get("previous_answer") or "").strip()

        if not form["subject"] or not form["topic"]:
            result = "Please enter both a subject and topic."
            source = "Validation"
        elif form["follow_up"] and previous_answer:
            result, source = generate_deepseek_tutor_followup(
                form["subject"],
                form["topic"],
                form["level"],
                form["style"],
                previous_answer,
                form["follow_up"],
                ai_agent=form["ai_agent"],
            )
            if not result:
                result, source = generate_gemini_tutor_followup(
                    form["subject"],
                    form["topic"],
                    form["level"],
                    form["style"],
                    previous_answer,
                    form["follow_up"],
                    api_key=gemini_key_for_user(user),
                )
            if not result:
                groq_answer = call_groq_text(
                    f"Answer this tutor follow-up clearly with Markdown and LaTeX where needed.\nSubject: {form['subject']}\nTopic: {form['topic']}\nLevel: {form['level']}\nPrevious answer:\n{previous_answer[:3500]}\nQuestion: {form['follow_up']}",
                    system_prompt="You are Suhana Tutor Pro: concise, accurate, exam-useful, and friendly. Use Markdown and LaTeX.",
                )
                if groq_answer:
                    result = groq_answer
                    source = "Groq Tutor"
            if not result:
                pollinations_answer = call_pollinations_text(
                    f"Answer this tutor follow-up clearly with Markdown and LaTeX where needed.\nSubject: {form['subject']}\nTopic: {form['topic']}\nLevel: {form['level']}\nPrevious answer:\n{previous_answer}\nQuestion: {form['follow_up']}"
                )
                if pollinations_answer:
                    result = pollinations_answer
                    source = "Pollinations AI"
            if not result:
                result, source = generate_openai_tutor_lesson(
                    form["subject"],
                    form["topic"],
                    form["level"],
                    form["style"],
                    f"{previous_answer}\n\nFollow-up: {form['follow_up']}",
                    api_key=openai_key_for_user(user),
                )
            if not result:
                if strict_ai_mode():
                    result = "## AI provider retry needed\n\nGemini and OpenAI did not return a usable tutor follow-up. Open `/ai-health` and check key validity, quota/billing, model access, and network. Strict AI mode is enabled, so Suhana AI will not show a fake fallback lesson."
                    source = "AI Provider Error"
                else:
                    result = fallback_tutor_lesson(
                        form["subject"],
                        form["topic"],
                        form["level"],
                        form["style"],
                        f"{previous_answer}\n\nFollow-up: {form['follow_up']}",
                    )
                    source = nim_agent_source(form["ai_agent"], "Tutor")
        else:
            result, source = generate_deepseek_tutor_lesson(
                form["subject"],
                form["topic"],
                form["level"],
                form["style"],
                resources=form["resources"],
                ai_agent=form["ai_agent"],
            )
            if not result:
                result, source = generate_gemini_tutor_lesson(
                    form["subject"],
                    form["topic"],
                    form["level"],
                    form["style"],
                    resources=form["resources"],
                    api_key=gemini_key_for_user(user),
                )
            if not result:
                groq_answer = call_groq_text(
                    f"Teach this topic as an AI tutor using Markdown and LaTeX where needed.\nSubject: {form['subject']}\nTopic: {form['topic']}\nLevel: {form['level']}\nStyle: {form['style']}\nResources: {form['resources']}",
                    system_prompt="You are Suhana Tutor Pro. Teach with simple intuition, formulas, one solved example, mistakes, revision notes, and practice questions. Keep it focused.",
                )
                if groq_answer:
                    result = groq_answer
                    source = "Groq Tutor"
            if not result:
                pollinations_answer = call_pollinations_text(
                    f"Teach this topic as an AI tutor using Markdown and LaTeX where needed.\nSubject: {form['subject']}\nTopic: {form['topic']}\nLevel: {form['level']}\nStyle: {form['style']}\nResources: {form['resources']}"
                )
                if pollinations_answer:
                    result = pollinations_answer
                    source = "Pollinations AI"
            if not result:
                result, source = generate_openai_tutor_lesson(
                    form["subject"],
                    form["topic"],
                    form["level"],
                    form["style"],
                    form["resources"],
                    api_key=openai_key_for_user(user),
                )
            if not result:
                if strict_ai_mode():
                    result = "## AI provider retry needed\n\nGemini and OpenAI did not return a usable tutor lesson. Open `/ai-health` and check key validity, quota/billing, model access, and network. Strict AI mode is enabled, so Suhana AI will not show a fake fallback lesson."
                    source = "AI Provider Error"
                else:
                    result = fallback_tutor_lesson(
                        form["subject"],
                        form["topic"],
                        form["level"],
                        form["style"],
                        form["resources"],
                    )
                    source = nim_agent_source(form["ai_agent"], "Tutor")

        if user and result and source != "Validation":
            save_user_work(
                user,
                "Tutor",
                f"{form['subject']} - {form['topic']}",
                form["follow_up"] or form["resources"] or form["topic"],
                result,
                source,
                url_for("ai_tutor"),
            )
            recent_tutor_work = SavedWork.query.filter_by(user_id=user.id, work_type="Tutor").order_by(SavedWork.id.desc()).limit(5).all()

    return render_template(
        "ai_tutor.html",
        result=result,
        result_html=render_ai_markdown(result) if result else None,
        source=source,
        form=form,
        recent_tutor_work=recent_tutor_work,
    )


@app.route("/suhana-code", methods=["GET", "POST"])
def suhana_code():
    result = None
    source = None
    user = current_user()
    recent_code_work = SavedWork.query.filter_by(user_id=user.id, work_type="Code").order_by(SavedWork.id.desc()).limit(5).all() if user else []
    form = {
        "query": "",
        "language": "Python",
        "mode": "DSA / Problem Solving",
        "follow_up": "",
        "ai_agent": "auto",
    }

    if request.method == "POST":
        form["query"] = (request.form.get("query") or "").strip()
        form["language"] = (request.form.get("language") or "").strip()
        form["mode"] = (request.form.get("mode") or "").strip()
        form["follow_up"] = (request.form.get("follow_up") or "").strip()
        form["ai_agent"] = (request.form.get("ai_agent") or "auto").strip()
        previous_answer = (request.form.get("previous_answer") or "").strip()
        effective_query = form["follow_up"] if form["follow_up"] and previous_answer else form["query"]
        if not form["query"]:
            result = "Please enter a coding question, bug, or DSA problem."
            source = "Validation"
        else:
            result, source = generate_suhana_code_answer(
                effective_query,
                form["language"],
                form["mode"],
                api_key_gemini=gemini_key_for_user(user),
                api_key_openai=openai_key_for_user(user),
                previous_answer=previous_answer,
                ai_agent=form["ai_agent"],
            )

        if user and result and source != "Validation":
            save_user_work(
                user,
                "Code",
                f"{form['language']} - {form['mode']}",
                effective_query,
                result,
                source,
                url_for("suhana_code"),
            )
            recent_code_work = SavedWork.query.filter_by(user_id=user.id, work_type="Code").order_by(SavedWork.id.desc()).limit(5).all()

    return render_template(
        "suhana_code.html",
        result=result,
        result_html=render_ai_markdown(result) if result else None,
        source=source,
        form=form,
        recent_code_work=recent_code_work,
    )


@app.route("/tutor-export-pdf", methods=["POST"])
def tutor_export_pdf():
    title = (request.form.get("title") or "Suhana AI Tutor Lesson").strip()
    content = (request.form.get("content") or "").strip()
    if not content:
        return redirect(url_for("ai_tutor"))
    os.makedirs(os.path.join("static", "tools"), exist_ok=True)
    output_file = f"tutor_lesson_{uuid.uuid4()}.pdf"
    output_path = os.path.join("static", "tools", output_file)
    if not write_text_pdf(title, content, output_path):
        return "Install Pillow first: pip install Pillow"
    return redirect(url_for("static", filename=f"tools/{output_file}"))


@app.route("/pdf-merge", methods=["GET", "POST"])
def pdf_merge():
    output_file = None
    message = None

    if request.method == "POST":
        operation = request.form.get("operation", "merge")
        valid_operations = {"merge", "jpg_to_pdf", "rotate_pdf", "compress_pdf", "image_compress"}
        if operation not in valid_operations:
            message = "Choose a valid document operation."
            return render_template("pdf_merge.html", output_file=output_file, message=message)
        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            return "Install pypdf first: pip install pypdf"

        os.makedirs(os.path.join("static", "tools"), exist_ok=True)

        if operation == "merge":
            files = request.files.getlist("pdfs")
            writer = PdfWriter()
            added = 0
            for file in files:
                if file and file.filename.lower().endswith(".pdf"):
                    temp_name = secure_filename(file.filename)
                    temp_path = os.path.join("static", "tools", f"temp_{uuid.uuid4()}_{temp_name}")
                    file.save(temp_path)
                    writer.append(temp_path)
                    added += 1
            if added:
                output_file = f"merged_{uuid.uuid4()}.pdf"
                output_path = os.path.join("static", "tools", output_file)
                with open(output_path, "wb") as f:
                    writer.write(f)
                message = f"Merged {added} PDF file(s)."
            else:
                message = "Upload at least two valid PDF files to merge."
            writer.close()

        elif operation in {"compress_pdf", "rotate_pdf"}:
            file = request.files.get("pdf")
            if file and file.filename.lower().endswith(".pdf"):
                temp_name = secure_filename(file.filename)
                temp_path = os.path.join("static", "tools", f"temp_{uuid.uuid4()}_{temp_name}")
                file.save(temp_path)
                reader = PdfReader(temp_path)
                writer = PdfWriter()
                angle = int(request.form.get("angle", "90") or 90)
                for page in reader.pages:
                    if operation == "rotate_pdf":
                        page.rotate(angle)
                    else:
                        try:
                            page.compress_content_streams()
                        except Exception:
                            pass
                    writer.add_page(page)
                output_file = f"{operation}_{uuid.uuid4()}.pdf"
                output_path = os.path.join("static", "tools", output_file)
                with open(output_path, "wb") as f:
                    writer.write(f)
                writer.close()
                message = "Rotated PDF ready." if operation == "rotate_pdf" else "Compressed PDF ready."
            else:
                message = "Upload one valid PDF file for this operation."

        elif operation in {"jpg_to_pdf", "image_compress"}:
            try:
                from PIL import Image, ImageOps
            except ImportError:
                return "Install Pillow first: pip install Pillow"
            images = request.files.getlist("images")
            opened = []
            for file in images:
                if file and allowed_upload(file.filename, {"png", "jpg", "jpeg", "webp"}):
                    temp_name = secure_filename(file.filename)
                    temp_path = os.path.join("static", "tools", f"temp_{uuid.uuid4()}_{temp_name}")
                    file.save(temp_path)
                    try:
                        img = ImageOps.exif_transpose(Image.open(temp_path)).convert("RGB")
                        opened.append(img)
                    except Exception:
                        message = "One uploaded image could not be read and was skipped."
            if opened and operation == "jpg_to_pdf":
                output_file = f"images_to_pdf_{uuid.uuid4()}.pdf"
                output_path = os.path.join("static", "tools", output_file)
                opened[0].save(output_path, save_all=True, append_images=opened[1:])
                message = f"Converted {len(opened)} image(s) to PDF."
            elif opened and operation == "image_compress":
                output_file = f"compressed_image_{uuid.uuid4()}.jpg"
                output_path = os.path.join("static", "tools", output_file)
                image = opened[0]
                max_size = int(request.form.get("max_size", "1600") or 1600)
                quality = int(request.form.get("quality", "64") or 64)
                max_size = max(640, min(max_size, 3000))
                quality = max(35, min(quality, 92))
                image.thumbnail((max_size, max_size))
                image.save(output_path, "JPEG", quality=quality, optimize=True)
                message = "Compressed image ready."
            elif not opened:
                message = message or "Upload a valid PNG, JPG, JPEG, or WEBP image."

    return render_template("pdf_merge.html", output_file=output_file, message=message)


@app.route("/image-editor", methods=["GET", "POST"])
def image_editor():
    output_file = None
    provider = None

    if request.method == "POST":
        try:
            from PIL import Image, ImageEnhance, ImageFilter, ImageOps
        except ImportError:
            return "Install Pillow first: pip install Pillow"

        image_file = request.files.get("image")
        operation = request.form.get("operation")
        ai_prompt = request.form.get("ai_prompt")
        strength = float(request.form.get("strength", 1.4) or 1.4)
        user = current_user()
        required_credits = 4 if operation == "ai_prompt" else 1

        if not user and not can_guest_generate("edit"):
            return trial_prompt("edit")
        if user and not has_credits(user, required_credits):
            return "Not enough credits. Switch to BYOK mode or add more credits."

        if image_file and image_file.filename:
            if not allowed_upload(image_file.filename, {"png", "jpg", "jpeg", "webp"}):
                return "Unsupported image type"

            os.makedirs(os.path.join("static", "tools"), exist_ok=True)
            filename = secure_filename(image_file.filename)
            input_path = os.path.join("static", "tools", f"input_{uuid.uuid4()}_{filename}")
            image_file.save(input_path)

            image = Image.open(input_path)
            image = ImageOps.exif_transpose(image).convert("RGB")

            if operation == "grayscale":
                image = ImageOps.grayscale(image).convert("RGB")
            elif operation == "contrast":
                image = ImageEnhance.Contrast(image).enhance(strength)
            elif operation == "brightness":
                image = ImageEnhance.Brightness(image).enhance(strength)
            elif operation == "color":
                image = ImageEnhance.Color(image).enhance(strength)
            elif operation == "sharpen":
                image = ImageEnhance.Sharpness(image).enhance(max(strength * 1.8, 1.0))
            elif operation == "soft_blur":
                image = image.filter(ImageFilter.GaussianBlur(radius=max(strength, 0.5)))
            elif operation == "edge_glow":
                edges = image.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(radius=1.2))
                edges = ImageEnhance.Color(edges).enhance(1.8)
                image = Image.blend(ImageEnhance.Contrast(image).enhance(1.12), edges, 0.18)
            elif operation == "thumbnail":
                image = ImageOps.fit(image, (1280, 720), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                image = ImageEnhance.Color(image).enhance(1.18)
                image = ImageEnhance.Contrast(image).enhance(1.18)
                image = ImageEnhance.Sharpness(image).enhance(1.35)
            elif operation == "square_canvas":
                size = max(image.size)
                canvas = Image.new("RGB", (size, size), (8, 10, 24))
                bg = ImageOps.fit(image.copy(), (size, size), method=Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(radius=24))
                canvas.paste(ImageEnhance.Brightness(bg).enhance(0.7), (0, 0))
                canvas.paste(image, ((size - image.width) // 2, (size - image.height) // 2))
                image = canvas
            elif operation == "background_blur":
                w, h = image.size
                bg = image.filter(ImageFilter.GaussianBlur(radius=18))
                fg = ImageOps.fit(image, (int(w * 0.86), int(h * 0.86)), method=Image.Resampling.LANCZOS)
                bg.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
                image = bg
            elif operation == "mirror":
                image = ImageOps.mirror(image)
            elif operation == "rotate":
                image = image.rotate(90, expand=True)
            elif operation == "sepia":
                gray = ImageOps.grayscale(image)
                image = ImageOps.colorize(gray, "#1c1220", "#f0d5a6").convert("RGB")
            elif operation == "auto_enhance":
                image = ImageOps.autocontrast(image)
                image = ImageEnhance.Color(image).enhance(1.18)
                image = ImageEnhance.Contrast(image).enhance(1.14)
                image = ImageEnhance.Sharpness(image).enhance(1.35)
            elif operation == "reel_crop":
                image = ImageOps.fit(image, (1080, 1920), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            elif operation == "vignette":
                w, h = image.size
                mask = Image.new("L", (w, h), 0)
                from PIL import ImageDraw
                draw = ImageDraw.Draw(mask)
                margin = int(min(w, h) * 0.08)
                draw.ellipse((margin, margin, w - margin, h - margin), fill=255)
                mask = mask.filter(ImageFilter.GaussianBlur(radius=int(min(w, h) * 0.18)))
                dark = ImageEnhance.Brightness(image).enhance(0.52)
                image = Image.composite(image, dark, mask)
            elif operation == "posterize":
                image = ImageOps.posterize(ImageEnhance.Color(image).enhance(1.25), 4)
                image = ImageEnhance.Contrast(image).enhance(1.22)
            elif operation == "watermark":
                from PIL import ImageDraw, ImageFont
                draw = ImageDraw.Draw(image)
                text = (request.form.get("watermark_text") or "SUHANA AI").strip()[:40]
                font = ImageFont.load_default()
                bbox = draw.textbbox((0, 0), text, font=font)
                pad = max(18, image.width // 60)
                x = image.width - (bbox[2] - bbox[0]) - pad
                y = image.height - (bbox[3] - bbox[1]) - pad
                draw.rounded_rectangle((x - 10, y - 8, image.width - pad + 10, image.height - pad + 8), radius=10, fill=(0, 0, 0))
                draw.text((x, y), text, fill=(125, 211, 252), font=font)

            output_file = f"edited_{uuid.uuid4()}.jpg"
            output_path = os.path.join("static", "tools", output_file)

            if operation == "ai_prompt" and ai_prompt:
                if edit_openai_image(input_path, ai_prompt, output_path, api_key=openai_key_for_user(user)):
                    provider = "OpenAI"
                else:
                    image = ImageOps.autocontrast(image)
                    image = ImageEnhance.Color(image).enhance(1.25)
                    image = ImageEnhance.Contrast(image).enhance(1.2)
                    image = ImageEnhance.Sharpness(image).enhance(1.25)
                    image.convert("RGB").save(output_path, "JPEG", quality=92)
                    provider = "AI fallback local polish"
            else:
                image.convert("RGB").save(output_path, "JPEG", quality=92)
                provider = "Local"

            consume_credits(user, required_credits)
            record_guest_generation("edit")

    return render_template("image_editor.html", output_file=output_file, provider=provider)


@app.route("/script-generator", methods=["GET", "POST"])
def script_generator():
    result = None

    if request.method == "POST":
        topic = request.form.get("topic")
        niche = request.form.get("niche")
        tone = request.form.get("tone")
        duration = request.form.get("duration")
        ai_agent = (request.form.get("ai_agent") or "auto").strip()

        user = current_user()
        script_usage_before = usage_count(user, "script")

        if not user and not can_guest_generate("script"):
            return trial_prompt("script")
        if user and not can_use_feature(user, "script"):
            return upgrade_prompt("script")

        hook, script_body, scene_plan, caption, hashtags, generation_source, error_message = generate_script_content(
            topic, niche, tone, duration, api_key=gemini_key_for_user(user), ai_agent=ai_agent
        )

        new_script = Script(
            user_id=session.get("user_id", 0),
            topic=topic,
            niche=niche,
            tone=tone,
            duration=duration,
            hook=hook,
            script_body=script_body,
            scene_plan=scene_plan,
            caption=caption,
            hashtags=hashtags,
            generation_source=generation_source,
            error_message=error_message
        )

        db.session.add(new_script)
        db.session.commit()
        charge_after_free_limit(user, "script", script_usage_before)
        record_guest_generation("script")

        result = new_script

    recent_scripts = []
    if "user_id" in session:
        recent_scripts = Script.query.filter_by(
            user_id=session["user_id"]
        ).order_by(Script.id.desc()).limit(5).all()

    return render_template(
        "script_generator.html",
        result=result,
        recent_scripts=recent_scripts
    )


@app.route("/script-feedback/<int:script_id>", methods=["POST"])
def script_feedback(script_id):
    script = Script.query.get(script_id)

    if not script:
        return "Script not found"

    if script.user_id != 0 and ("user_id" not in session or script.user_id != session["user_id"]):
        return "You do not have access to this script"

    rating = int(request.form.get("rating", 5))
    edited_script = request.form.get("edited_script")
    notes = request.form.get("notes")

    feedback = ScriptFeedback(
        script_id=script.id,
        user_id=session.get("user_id", 0),
        rating=rating,
        edited_script=edited_script,
        notes=notes
    )
    db.session.add(feedback)
    db.session.commit()

    return redirect(url_for("script_generator"))


@app.route("/experience-feedback", methods=["POST"])
def experience_feedback():
    feature = request.form.get("feature", "general")
    target_id = request.form.get("target_id")
    rating = int(request.form.get("rating", 5) or 5)
    notes = request.form.get("notes")

    feedback = ExperienceFeedback(
        user_id=session.get("user_id", 0),
        feature=feature[:50],
        target_id=int(target_id) if target_id and target_id.isdigit() else None,
        rating=max(1, min(rating, 5)),
        notes=notes,
    )
    db.session.add(feedback)
    db.session.commit()

    if feature == "reel" and target_id:
        reel = Reel.query.get(int(target_id))
        if reel:
            return redirect(url_for("reel_status", folder_id=reel.folder_id))

    return redirect(url_for("dashboard") if "user_id" in session else url_for("home"))


with app.app_context():
    ensure_schema()

@app.route("/script-to-reel/<int:script_id>")
def script_to_reel(script_id):
    script = Script.query.get(script_id)

    if not script:
        return "Script not found"

    if script.user_id != 0:
        if "user_id" not in session:
            return redirect(url_for("login"))

        if script.user_id != session["user_id"]:
            return "You do not have access to this script"

    session["prefill_script"] = script.script_body

    return redirect(url_for("create"))


@app.route("/visual-studio", methods=["GET", "POST"])
def visual_studio():
    selected_type = request.args.get("type", "image")
    if selected_type not in ["image", "video"]:
        selected_type = "image"
    return visual_studio_page(default_asset_type=selected_type)


@app.route("/ai-images", methods=["GET", "POST"])
def ai_images():
    return visual_studio_page(default_asset_type="image")


@app.route("/ai-video", methods=["GET", "POST"])
def ai_video():
    return visual_studio_page(default_asset_type="video")


def visual_studio_page(default_asset_type="image"):
    result = None
    provider = None

    if request.method == "POST":
        prompt = request.form.get("prompt")
        aspect_ratio = normalize_aspect_ratio(request.form.get("aspect_ratio"), "16:9" if default_asset_type == "video" else "9:16")
        preferred_model = request.form.get("preferred_model", "auto")
        asset_type = default_asset_type
        user = current_user()
        image_usage_before = usage_count(user, "image")

        if not user and not can_guest_generate("image" if asset_type == "image" else "video"):
            return trial_prompt("image" if asset_type == "image" else "video")
        if user and asset_type == "image" and not can_use_feature(user, "image"):
            return upgrade_prompt("image")

        os.makedirs(os.path.join("static", "tools"), exist_ok=True)

        if asset_type == "image":
            output_file = f"visual_{uuid.uuid4()}.png"
            output_path = os.path.join("static", "tools", output_file)
            provider = generate_ai_image_asset(
                prompt,
                output_path,
                user=user,
                aspect_ratio=aspect_ratio,
                preferred_model=preferred_model,
            )
            if not provider:
                create_placeholder_asset(prompt, output_path, label="AI Image Concept")
                provider = "Fallback"
        else:
            output_file = f"storyboard_{uuid.uuid4()}.png"
            output_path = os.path.join("static", "tools", output_file)
            provider = generate_ai_image_asset(
                prompt,
                output_path,
                user=user,
                aspect_ratio=aspect_ratio,
                preferred_model=preferred_model,
                asset_type="video",
            )
            if not provider:
                create_placeholder_asset(prompt, output_path, label="AI Video Coming Soon")
                provider = "Coming Soon"

        asset = VisualAsset(
            user_id=session.get("user_id", 0),
            asset_type=asset_type,
            prompt=prompt or "",
            file_path=output_file,
            provider=provider
        )
        db.session.add(asset)
        db.session.commit()
        if asset_type == "image":
            charge_after_free_limit(user, "image", image_usage_before)
        record_guest_generation("image" if asset_type == "image" else "video")
        result = asset

    recent_assets = []
    if "user_id" in session:
        recent_assets = VisualAsset.query.filter_by(
            user_id=session["user_id"],
            asset_type=default_asset_type
        ).order_by(VisualAsset.id.desc()).limit(6).all()

    return render_template(
        "visual_studio.html",
        result=result,
        recent_assets=recent_assets,
        default_asset_type=default_asset_type
    )


@app.route("/asset-to-reel/<int:asset_id>")
def asset_to_reel(asset_id):
    asset = VisualAsset.query.get(asset_id)

    if not asset:
        return "Asset not found"

    if asset.user_id != 0:
        if "user_id" not in session:
            return redirect(url_for("login"))
        if asset.user_id != session["user_id"]:
            return "You do not have access to this asset"

    session["prefill_visual_prompt"] = asset.prompt
    session["prefill_asset_file"] = asset.file_path

    return redirect(url_for("create"))


@app.route("/billing", methods=["GET", "POST"])
def billing():
    if "user_id" not in session:
        return redirect(url_for("pricing"))

    user = current_user()

    if request.method == "POST":
        if not is_admin_user(user):
            return redirect(url_for("pricing"))
        pack = request.form.get("pack")
        packs = {
            "starter": 25,
            "creator": 100,
            "agency": 500,
        }
        credits = packs.get(pack, 0)
        if credits:
            add_credits(user, credits, f"Dev billing pack: {pack}")
        return redirect(url_for("billing"))

    transactions = CreditTransaction.query.filter_by(
        user_id=user.id
    ).order_by(CreditTransaction.id.desc()).limit(20).all()

    return render_template("billing.html", user=user, transactions=transactions, is_admin=is_admin_user(user))


@app.route("/dev/users")
def dev_users():
    if os.getenv("ENABLE_DEV_ADMIN") != "1":
        return "Dev admin is disabled. Set ENABLE_DEV_ADMIN=1 in .env to use this local tool."

    users = User.query.order_by(User.id.desc()).all()
    return render_template("dev_users.html", users=users)


@app.route("/dev/add-credits/<int:user_id>", methods=["POST"])
def dev_add_credits(user_id):
    if os.getenv("ENABLE_DEV_ADMIN") != "1":
        return "Dev admin is disabled."

    user = User.query.get(user_id)
    if not user:
        return "User not found"
    amount = int(request.form.get("amount", 25))
    add_credits(user, amount, "Dev admin credit adjustment")
    return redirect(url_for("dev_users"))

def run_worker_loop():
    from worker import process_queue_once

    print("Background worker started")

    while True:
        process_queue_once()
        time.sleep(4)


_worker_started = False


def start_background_worker():
    global _worker_started
    if os.getenv("START_BACKGROUND_WORKER", "0") != "1":
        return
    if _worker_started:
        return

    worker_thread = threading.Thread(target=run_worker_loop, daemon=True)
    worker_thread.start()
    _worker_started = True


if __name__ == "__main__":
    start_background_worker()

    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
