# API Endpoints

## Overview
This document lists the available API endpoints in the FastAPI app, their purpose, dummy request payloads, and sample outputs or error responses.

Base path: `/api/v1`

---

## Health

### GET /health/
- Purpose: Verify the service is running.
- Sample request: `GET /api/v1/health/`
- Response:
  - Status: `200`
  - Body:
    ```json
    {"status": "ok"}
    ```

---

## Auth

### POST /auth/token
- Purpose: Create or sign in a Google-authenticated user and return a bearer token.
- Dummy request:
  ```json
  {
    "google_sub": "dummy-user-123",
    "email": "dummy@example.com",
    "name": "Dummy User"
  }
  ```
- Sample response:
  - Status: `200`
  - Body includes `access_token`, `token_type`, `expires_at`, and `user` object.

### POST /auth/email/signup
- Purpose: Register a user by email/password and issue a session token.
- Dummy request:
  ```json
  {
    "email": "user@example.com",
    "password": "StrongP@ssw0rd!",
    "name": "Email User"
  }
  ```
- Response:
  - Status: `200`
  - Body: same shape as `/auth/token` response.

### POST /auth/email/login
- Purpose: Authenticate an existing email/password user.
- Dummy request:
  ```json
  {
    "email": "user@example.com",
    "password": "StrongP@ssw0rd!"
  }
  ```
- Response:
  - Status: `200`
  - Body: same shape as `/auth/token` response.

### POST /auth/github/login
- Purpose: Create or sign in a GitHub-authenticated user with GitHub ID.
- Dummy request:
  ```json
  {
    "github_id": "gh-test-user",
    "email": "github@example.com",
    "name": "GitHub User"
  }
  ```
- Response:
  - Status: `200`
  - Body: same shape as `/auth/token` response.

### POST /auth/guest
- Purpose: Create a temporary guest session user.
- Dummy request: none required.
- Response:
  - Status: `200`
  - Body: same shape as `/auth/token` response.

### POST /auth/logout
- Purpose: Revoke the current bearer token session.
- Request header: `Authorization: Bearer <token>`
- Sample response:
  - Status: `200`
  - Body:
    ```json
    {"detail": "Logged out successfully"}
    ```

### GET /auth/me
- Purpose: Return the authenticated user's profile.
- Request header: `Authorization: Bearer <token>`
- Response:
  - Status: `200`
  - Body: user profile data.

### GET /auth/google/authorize
- Purpose: Return the Google OAuth authorization URL.
- Response:
  - Status: `200`
  - Body: `{ "authorization_url": "..." }`

### GET /auth/callback
- Purpose: Complete Google OAuth callback and issue a token.
- Query: `?code=<google-code>`
- Response: `200` plus session payload on success.

### GET /auth/github/authorize
- Purpose: Return the GitHub OAuth authorization URL.
- Response:
  - Status: `200`
  - Body: `{ "authorization_url": "..." }`

### GET /auth/github/callback
- Purpose: Complete GitHub OAuth callback and issue a token.
- Query: `?code=<github-code>`
- Response: `200` plus session payload on success.

---

## Analyze

### POST /analyze/text
- Purpose: Analyze a code snippet with OpenRouter.
- Dummy request:
  ```json
  {
    "code": "def hello():\n    return 'world'",
    "language": "python",
    "filename": "hello.py"
  }
  ```
- In the current environment, this returned:
  - Status: `503`
  - Body:
    ```json
    {"detail": "OpenRouter API key is not configured. Set OPENROUTER_API_KEY in .env."}
    ```
- Note: This endpoint requires a valid `OPENROUTER_API_KEY` to work.

### POST /analyze/file
- Purpose: Analyze a source file upload.
- Dummy request: multipart form file `file=hello.py` containing Python code.
- In the current environment, this returned:
  - Status: `503`
  - Body:
    ```json
    {"detail": "OpenRouter API key is not configured. Set OPENROUTER_API_KEY in .env."}
    ```
- Note: This endpoint also requires `OPENROUTER_API_KEY`.

### POST /analyze/save
- Purpose: Save analysis results for the authenticated user.
- Dummy request:
  ```json
  {
    "code": "def hello():\n    return 'world'",
    "filename": "hello.py",
    "language": "python",
    "summary": "Dummy analysis",
    "nodes": [],
    "edges": [],
    "diagnostics": [],
    "fixed_code": null
  }
  ```
- Sample response:
  - Status: `200`
  - Body:
    ```json
    {
      "id": 1,
      "user_id": 21,
      "code": "def hello():\n    return 'world'",
      "filename": "hello.py",
      "language": "python",
      "summary": "Dummy analysis",
      "nodes": [],
      "edges": [],
      "diagnostics": [],
      "fixed_code": null,
      "created_at": "2026-07-16T09:59:09",
      "updated_at": "2026-07-16T09:59:09"
    }
    ```

### GET /analyze/history
- Purpose: List saved analyses for the authenticated user.
- Sample response:
  - Status: `200`
  - Body: an array of saved history objects.

### GET /analyze/history/{analysis_id}
- Purpose: Fetch one saved analysis by ID.
- Sample response:
  - Status: `200`
  - Body: the saved analysis object.

### DELETE /analyze/history/{analysis_id}
- Purpose: Remove a saved analysis.
- Sample response:
  - Status: `204`
  - Body: empty

---

## Error cases seen during dummy runs

- `POST /analyze/text` with blank code returned `400`:
  ```json
  {"detail": "Code payload cannot be empty."}
  ```
- `POST /analyze/file` with unsupported extension returned `400`:
  ```json
  {"detail": "Unsupported file extension: .exe"}
  ```
- `GET /api/v1/analyze/history/{id}` for deleted item returned `404`:
  ```json
  {"detail": "Analysis not found"}
  ```

---

## Notes

- The analysis routes depend on `OPENROUTER_API_KEY` for actual LLM-based analysis.
- The current auth/session routes work with bearer tokens issued from `/auth/token`, `/auth/email/signup`, `/auth/email/login`, `/auth/github/login`, or `/auth/guest`.
- The project test run for `tests/test_analyze.py` passed with `16 passed` in `.venv`.
