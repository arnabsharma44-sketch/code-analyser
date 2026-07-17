import httpx
from fastapi import HTTPException

from app.core.config import settings

RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"
HCAPTCHA_VERIFY_URL = "https://hcaptcha.com/siteverify"


async def verify_captcha_token(token: str | None) -> None:
    provider = settings.get_captcha_provider()
    if provider == "none":
        return

    if not token:
        raise HTTPException(status_code=400, detail="CAPTCHA token is required")

    if provider == "recaptcha":
        secret = settings.get_recaptcha_secret_key()
        if not secret:
            raise HTTPException(status_code=503, detail="reCAPTCHA secret key is not configured")
        await _verify_recaptcha(token, secret)
        return

    if provider == "hcaptcha":
        secret = settings.get_hcaptcha_secret_key()
        if not secret:
            raise HTTPException(status_code=503, detail="hCaptcha secret key is not configured")
        await _verify_hcaptcha(token, secret)
        return

    raise HTTPException(status_code=400, detail=f"Unsupported CAPTCHA provider: {provider}")


async def _verify_recaptcha(token: str, secret: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            RECAPTCHA_VERIFY_URL,
            data={"secret": secret, "response": token},
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Unable to verify reCAPTCHA token")

    data = response.json()
    if not data.get("success"):
        raise HTTPException(status_code=400, detail="Invalid reCAPTCHA token")


async def _verify_hcaptcha(token: str, secret: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            HCAPTCHA_VERIFY_URL,
            data={"secret": secret, "response": token},
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Unable to verify hCaptcha token")

    data = response.json()
    if not data.get("success"):
        raise HTTPException(status_code=400, detail="Invalid hCaptcha token")
