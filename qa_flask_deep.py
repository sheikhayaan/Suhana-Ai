import re
import uuid

from main import SavedWork, app, db, ensure_schema


def csrf_from(response):
    match = re.search(r'name="_csrf_token" value="([^"]+)"', response.get_data(as_text=True))
    return match.group(1) if match else ""


def report(label, response, expected=(200, 302)):
    ok = response.status_code in expected
    print(f"{'OK' if ok else 'FAIL'} {label}: {response.status_code} bytes={len(response.get_data())}")
    return ok


def signup_client():
    client = app.test_client()
    page = client.get("/signup?next=/dashboard")
    token = csrf_from(page)
    email = f"deep_{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/signup",
        data={
            "_csrf_token": token,
            "next": "/dashboard",
            "purpose": "engineer",
            "primary_goal": "debug a launch app",
            "name": "Deep QA",
            "email": email,
            "password": "password123",
        },
    )
    return client, response


def main():
    failures = 0
    with app.app_context():
        ensure_schema()

    client, signup = signup_client()
    failures += not report("signup deep user", signup, expected=(302,))

    authed_pages = [
        "/dashboard",
        "/settings",
        "/api-vault",
        "/gallery",
        "/billing",
        "/mission",
        "/studio",
        "/tools",
        "/create",
        "/ai-bridge",
        "/brand-memory",
        "/workflow-builder",
        "/creator-copilot",
        "/performance-coach",
        "/ml-growth-lab",
        "/startup-analyzer",
        "/avatar-maker",
        "/visual-studio",
        "/ai-images",
        "/ai-video",
    ]
    for path in authed_pages:
        failures += not report(f"GET authed {path}", client.get(path), expected=(200, 302))

    with app.app_context():
        saved = SavedWork(
            user_id=1,
            work_type="QA",
            title="Manual Saved Work Check",
            prompt="test prompt",
            output="# Saved output\n\nThis should render.",
            source="QA",
            href="/dashboard",
        )
        db.session.add(saved)
        db.session.commit()
        saved_id = saved.id

    # This may redirect if saved_id belongs to another user; the route must not 500.
    failures += not report("GET saved work access safety", client.get(f"/saved-work/{saved_id}"), expected=(200, 302))

    print(f"FAILURES={int(failures)}")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
