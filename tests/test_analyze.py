import asyncio
import json
import uuid

import httpx
import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, patch
from pydantic import SecretStr

from app.core.config import settings
from app.main import app
from app.schemas.analysis import AnalyserGraphResponse
from app.services.diagnostics import collect_diagnostics
from app.services.llm_chain import run_code_analysis


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def auth_headers():
    async def _make_headers():
        response = await request("POST", "/api/v1/auth/token", json={
            "google_sub": "test-user",
            "email": "test@example.com",
            "name": "Test User",
        })
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _make_headers


async def request(method: str, url: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.request(method, url, **kwargs)


@pytest.fixture(autouse=True)
def disable_captcha_in_tests(monkeypatch):
    async def _verify_captcha_token(token):
        return None

    monkeypatch.setattr("app.api.v1.endpoints.auth.verify_captcha_token", _verify_captcha_token)


@pytest.mark.anyio
async def test_health():
    response = await request("GET", "/api/v1/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

@patch("app.api.v1.endpoints.analyze.run_code_analysis", new_callable=AsyncMock)
@pytest.mark.anyio
async def test_analyze_text_valid(mock_run_code_analysis, auth_headers):
    mock_run_code_analysis.return_value = AnalyserGraphResponse(
        summary="Test summary",
        nodes=[],
        edges=[],
        fixed_code="def test(): pass"
    )
    
    response = await request(
        "POST",
        "/api/v1/analyze/text",
        json={"code": "def test():\npass", "language": "python"},
        headers=await auth_headers(),
    )
    
    assert response.status_code == 200
    assert response.json()["summary"] == "Test summary"

@pytest.mark.anyio
async def test_analyze_text_empty(auth_headers):
    response = await request(
        "POST",
        "/api/v1/analyze/text",
        json={"code": ""},
        headers=await auth_headers(),
    )
    assert response.status_code == 422
    
@pytest.mark.anyio
async def test_analyze_text_blank(auth_headers):
    response = await request(
        "POST",
        "/api/v1/analyze/text",
        json={"code": "   "},
        headers=await auth_headers(),
    )
    assert response.status_code == 400

def test_run_code_analysis_missing_api_key():
    original_api_key = settings.openrouter_api_key
    settings.openrouter_api_key = SecretStr("   ")

    try:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(run_code_analysis("print('hello')", language="python"))
    finally:
        settings.openrouter_api_key = original_api_key

    assert exc_info.value.status_code == 503
    assert "OpenRouter API key is not configured" in exc_info.value.detail

@pytest.mark.anyio
async def test_auth_flow_creates_user_and_me_endpoint(auth_headers):
    headers = await auth_headers()
    me_response = await request("GET", "/api/v1/auth/me", headers=headers)

    assert me_response.status_code == 200
    assert me_response.json()["email"] == "test@example.com"


@pytest.mark.anyio
async def test_logout_revokes_session(auth_headers):
    headers = await auth_headers()

    logout_response = await request("POST", "/api/v1/auth/logout", headers=headers)
    assert logout_response.status_code == 200
    assert logout_response.json()["detail"] == "Logged out successfully"

    me_response = await request("GET", "/api/v1/auth/me", headers=headers)
    assert me_response.status_code == 401


@pytest.mark.anyio
async def test_email_signup_and_login():
    email = f"signup-{uuid.uuid4().hex[:8]}@example.com"

    signup_response = await request(
        "POST",
        "/api/v1/auth/email/signup",
        json={"email": email, "password": "strong-password", "name": "Email User"},
    )
    assert signup_response.status_code == 200

    login_response = await request(
        "POST",
        "/api/v1/auth/email/login",
        json={"email": email, "password": "strong-password"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["user"]["email"] == email


@pytest.mark.anyio
async def test_captcha_config_returns_hcaptcha_site_key():
    original_provider = settings.captcha_provider
    original_site_key = settings.hcaptcha_site_key
    try:
        settings.captcha_provider = "hcaptcha"
        settings.hcaptcha_site_key = "316a8b06-1878-49a2-b940-bfca3e26f6bc"

        response = await request("GET", "/api/v1/auth/captcha")
        assert response.status_code == 200
        assert response.json() == {
            "provider": "hcaptcha",
            "site_key": "316a8b06-1878-49a2-b940-bfca3e26f6bc",
        }
    finally:
        settings.captcha_provider = original_provider
        settings.hcaptcha_site_key = original_site_key


@pytest.mark.anyio
async def test_github_and_guest_login():
    github_response = await request(
        "POST",
        "/api/v1/auth/github/login",
        json={"github_id": "gh-test-user", "email": "github@example.com", "name": "GitHub User"},
    )
    assert github_response.status_code == 200

    guest_response = await request("POST", "/api/v1/auth/guest")
    assert guest_response.status_code == 200
    assert guest_response.json()["user"]["email"].startswith("guest-")
    assert guest_response.json()["user"]["email"].endswith("@example.com")


@pytest.mark.anyio
async def test_analyze_text_requires_auth():
    response = await request(
        "POST",
        "/api/v1/analyze/text",
        json={"code": "def test():\npass", "language": "python"},
    )

    assert response.status_code == 401


def test_collect_python_syntax_diagnostics():
    diagnostics = collect_diagnostics("def broken(:\n    pass", language="python")

    assert len(diagnostics) == 1
    assert diagnostics[0].source == "python-compiler"
    assert diagnostics[0].severity == "error"
    assert diagnostics[0].line == 1

def test_collect_json_parse_diagnostics_from_filename():
    diagnostics = collect_diagnostics('{"missing": }', filename="payload.json")

    assert len(diagnostics) == 1
    assert diagnostics[0].source == "json-parser"
    assert diagnostics[0].severity == "error"

def test_run_code_analysis_uses_openrouter_and_includes_diagnostics():
    original_api_key = settings.openrouter_api_key
    settings.openrouter_api_key = SecretStr("test-key")
    captured = {}

    response_body = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "summary": "Test summary",
                        "nodes": [],
                        "edges": [],
                        "diagnostics": [],
                    })
                }
            }
        ]
    }

    class FakeResponse:
        def __init__(self, status_code: int = 200, text: str | None = None):
            self.status_code = status_code
            self._text = text if text is not None else json.dumps(response_body)

        def json(self):
            return response_body

        @property
        def text(self):
            return self._text

    async def fake_post(self, *args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeResponse()

    try:
        with patch("app.services.llm_chain.httpx.AsyncClient.post", new=fake_post):
            response = asyncio.run(run_code_analysis("def broken(:\n    pass", language="python"))
    finally:
        settings.openrouter_api_key = original_api_key

    assert response.summary == "Test summary"
    assert response.diagnostics[0].source == "python-compiler"
    assert "Trusted local compiler/linter diagnostics" in captured["kwargs"]["json"]["messages"][1]["content"]

@patch("app.api.v1.endpoints.analyze.run_code_analysis", new_callable=AsyncMock)
@pytest.mark.anyio
async def test_analyze_file_valid(mock_run_code_analysis, auth_headers):
    mock_run_code_analysis.return_value = AnalyserGraphResponse(
        summary="File test summary",
        nodes=[],
        edges=[],
    )
    
    files = {'file': ('test.py', b"def hello(): pass")}
    response = await request("POST", "/api/v1/analyze/file", files=files, headers=await auth_headers())
    
    assert response.status_code == 200
    assert response.json()["summary"] == "File test summary"

@pytest.mark.anyio
async def test_delete_saved_analysis(auth_headers):
    headers = await auth_headers()

    payload = {
        "code": "def delete_test():\n    pass",
        "filename": "delete_test.py",
        "language": "python",
        "summary": "Delete test",
        "nodes": [],
        "edges": [],
        "diagnostics": [],
        "fixed_code": None,
    }

    save_response = await request("POST", "/api/v1/analyze/save", json=payload, headers=headers)
    assert save_response.status_code == 200
    analysis_id = save_response.json()["id"]

    delete_response = await request("DELETE", f"/api/v1/analyze/history/{analysis_id}", headers=headers)
    assert delete_response.status_code == 204

    get_response = await request("GET", f"/api/v1/analyze/history/{analysis_id}", headers=headers)
    assert get_response.status_code == 404

@pytest.mark.anyio
async def test_analyze_file_invalid_extension(auth_headers):
    files = {'file': ('test.exe', b"binary data")}
    response = await request("POST", "/api/v1/analyze/file", files=files, headers=await auth_headers())
    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["detail"]
