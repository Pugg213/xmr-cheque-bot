"""Configuration management using pydantic-settings."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Allow extra env vars without error
    )

    # Telegram
    bot_token: str = Field(..., description="Telegram bot token from @BotFather")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")

    # Monero RPC
    monero_rpc_url: str = Field(
        default="http://localhost:18083/json_rpc", description="monero-wallet-rpc URL"
    )

    # Encryption
    view_key_encryption_key: str = Field(
        ..., description="Fernet key for encrypting view keys (32 bytes base64)"
    )

    # CoinGecko
    coingecko_api_key: str | None = Field(default=None, description="Optional CoinGecko API key")

    # Logging
    log_level: str = Field(
        default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )

    # App settings
    app_mode: str = Field(default="both", description="Application mode: bot|monitor|both")
    max_active_cheques_per_user: int = Field(
        default=10, description="Maximum number of active cheques per user"
    )
    cheque_ttl_seconds: int = Field(default=3600, description="Cheque time-to-live in seconds")
    confirmations_final: int = Field(
        default=6, description="Number of confirmations for final status"
    )
    monitor_interval_sec: int = Field(
        default=30, description="Payment monitor polling interval in seconds"
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the allowed values."""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    @field_validator("view_key_encryption_key")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        """Validate encryption key format (base64, 32 bytes when decoded)."""
        import base64

        try:
            decoded = base64.urlsafe_b64decode(v)
            if len(decoded) != 32:
                raise ValueError("Encryption key must decode to 32 bytes")
        except Exception as e:
            raise ValueError(f"Invalid encryption key: {e}")
        return v


# Global settings instance (lazy loading)
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get cached settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
