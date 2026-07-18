from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    project_name: str = "Code Analyser API"
    database_url: str | None = None
    database_path: str = "app.db"
    auth_secret_key: SecretStr
    auth_session_ttl_seconds: int = 60 * 60 * 24 * 7
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: SecretStr | None = None
    google_oauth_redirect_uri: str = "http://localhost:8000/api/v1/auth/callback"
    github_oauth_client_id: str | None = None
    github_oauth_client_secret: SecretStr | None = None
    github_oauth_redirect_uri: str = "http://localhost:8000/api/v1/auth/github/callback"
    captcha_provider: str = "none"
    recaptcha_site_key: str | None = None
    recaptcha_secret_key: SecretStr | None = None
    hcaptcha_site_key: str | None = None
    hcaptcha_secret_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "OPENROUTER_KEY", "openrouter_api_key"),
    )
    openrouter_model: str = "openai/gpt-4o"
    cors_origins: list[str] = ["http://localhost:3000"]
    max_upload_bytes: int = 200_000
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    def get_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.database_path}"

    def get_auth_secret_key(self) -> str:
        if self.auth_secret_key is None:
            raise RuntimeError("AUTH_SECRET_KEY must be configured")
        return self.auth_secret_key.get_secret_value().strip()

    def get_openrouter_api_key(self) -> str | None:
        if self.openrouter_api_key is None:
            return None
        api_key = self.openrouter_api_key.get_secret_value().strip()
        return api_key or None

    def get_google_oauth_client_secret(self) -> str | None:
        if self.google_oauth_client_secret is None:
            return None
        secret = self.google_oauth_client_secret.get_secret_value().strip()
        return secret or None

    def get_github_oauth_client_secret(self) -> str | None:
        if self.github_oauth_client_secret is None:
            return None
        secret = self.github_oauth_client_secret.get_secret_value().strip()
        return secret or None

    def get_recaptcha_secret_key(self) -> str | None:
        if self.recaptcha_secret_key is None:
            return None
        secret = self.recaptcha_secret_key.get_secret_value().strip()
        return secret or None

    def get_recaptcha_site_key(self) -> str | None:
        if self.recaptcha_site_key is None:
            return None
        site_key = self.recaptcha_site_key.strip()
        return site_key or None

    def get_hcaptcha_site_key(self) -> str | None:
        if self.hcaptcha_site_key is None:
            return None
        site_key = self.hcaptcha_site_key.strip()
        return site_key or None

    def get_hcaptcha_secret_key(self) -> str | None:
        if self.hcaptcha_secret_key is None:
            return None
        secret = self.hcaptcha_secret_key.get_secret_value().strip()
        return secret or None

    def get_captcha_provider(self) -> str:
        return self.captcha_provider.strip().lower()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()
