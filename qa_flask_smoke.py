import re
import uuid

from main import app, db, ensure_schema


def csrf_from(response):
    text = response.get_data(as_text=True)
    match = re.search(r'name="_csrf_token" value="([^"]+)"', text)
    return match.group(1) if match else ""


def report(label, response, expected=(200, 302)):
    ok = response.status_code in expected
    print(f"{'OK' if ok else 'FAIL'} {label}: {response.status_code} bytes={len(response.get_data())}")
    return ok


def main():
    failures = 0
    with app.app_context():
        ensure_schema()

    client = app.test_client()

    public_gets = [
        "/",
        "/mission",
        "/tools",
        "/pricing",
        "/about",
        "/privacy",
        "/terms",
        "/ai-tutor",
        "/ai-quiz",
        "/suhana-code",
        "/pdf-merge",
        "/image-editor",
        "/script-generator",
        "/healthz",
    ]
    for path in public_gets:
        failures += not report(f"GET {path}", client.get(path), expected=(200,))

    failures += not report("GET /dashboard redirects", client.get("/dashboard"), expected=(302,))

    signup_page = client.get("/signup?next=/mission")
    failures += not report("GET /signup", signup_page, expected=(200,))
    token = csrf_from(signup_page)
    email = f"qa_{uuid.uuid4().hex[:10]}@example.com"
    signup = client.post(
        "/signup",
        data={
            "_csrf_token": token,
            "next": "/mission",
            "purpose": "student",
            "primary_goal": "QA launch test goal",
            "name": "QA User",
            "email": email,
            "password": "password123",
        },
        follow_redirects=False,
    )
    failures += not report("POST /signup", signup, expected=(302,))

    logged_in_gets = ["/dashboard", "/mission", "/ai-tutor", "/suhana-code", "/billing"]
    for path in logged_in_gets:
        failures += not report(f"GET logged {path}", client.get(path), expected=(200,))

    # Exercise validation branches and lightweight fallbacks without forcing expensive media work.
    tutor_page = client.get("/ai-tutor")
    tutor_token = csrf_from(tutor_page)
    tutor_post = client.post(
        "/ai-tutor",
        data={
            "_csrf_token": tutor_token,
            "subject": "",
            "topic": "",
            "level": "Class 10",
            "style": "Simple and practical",
            "resources": "",
            "ai_agent": "auto",
        },
    )
    failures += not report("POST /ai-tutor validation", tutor_post, expected=(200,))

    code_page = client.get("/suhana-code")
    code_token = csrf_from(code_page)
    code_post = client.post(
        "/suhana-code",
        data={
            "_csrf_token": code_token,
            "language": "Python",
            "mode": "DSA / Problem Solving",
            "query": "",
            "ai_agent": "auto",
        },
    )
    failures += not report("POST /suhana-code validation", code_post, expected=(200,))

    quiz_page = client.get("/ai-quiz")
    quiz_token = csrf_from(quiz_page)
    quiz_post = client.post(
        "/ai-quiz",
        data={
            "_csrf_token": quiz_token,
            "action": "generate",
            "topic": "",
            "level": "Class 10",
            "quiz_type": "Exam practice",
            "count": "5",
            "ai_agent": "auto",
        },
    )
    failures += not report("POST /ai-quiz validation", quiz_post, expected=(200,))

    mission_page = client.get("/mission")
    mission_token = csrf_from(mission_page)
    mission_post = client.post(
        "/mission",
        data={
            "_csrf_token": mission_token,
            "role": "student",
            "goal": "",
            "audience": "",
            "timeline": "7 days",
            "success_metric": "",
            "ai_agent": "auto",
        },
    )
    failures += not report("POST /mission validation", mission_post, expected=(200,))

    print(f"FAILURES={int(failures)}")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
