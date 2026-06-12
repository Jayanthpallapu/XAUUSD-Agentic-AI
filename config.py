import os
from pathlib import Path
from dotenv import load_dotenv

# Load env variables from .env if it exists
dotenv_path = Path(__file__).resolve().parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
else:
    load_dotenv()


class Settings:
    PORT: int = int(os.getenv("PORT", 8000))

    # LLM Settings — Hermes 3 via OpenRouter (primary) + Groq (failover)
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    # Supabase Settings
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    # Frontend URL for CORS (comma-separated for multiple origins)
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # Telegram settings
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Financial APIs
    ALPHA_VANTAGE_API_KEY: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    TWELVE_DATA_API_KEY: str = os.getenv("TWELVE_DATA_API_KEY", "")
    FRED_API_KEY: str = os.getenv("FRED_API_KEY", "")
    FMP_API_KEY: str = os.getenv("FMP_API_KEY", "")
    COINGECKO_API_KEY: str = os.getenv("COINGECKO_API_KEY", "")
    FINNHUB_API_KEY: str = os.getenv("FINNHUB_API_KEY", "")

    # Run intervals
    RUN_INTERVAL_MINUTES: int = int(os.getenv("RUN_INTERVAL_MINUTES", 15))

    @property
    def is_supabase_configured(self) -> bool:
        if not self.SUPABASE_KEY:
            return False
        # Safety check: ignore placeholder values
        placeholders = ["placeholder", "paste_your", "your_supabase", "your-supabase"]
        if any(p in self.SUPABASE_KEY.lower() for p in placeholders):
            return False
        return bool(self.SUPABASE_URL)

    @property
    def is_telegram_configured(self) -> bool:
        return bool(self.TELEGRAM_BOT_TOKEN and self.TELEGRAM_CHAT_ID)

    @property
    def is_openrouter_configured(self) -> bool:
        """True if OpenRouter API key is set and not a placeholder."""
        if not self.OPENROUTER_API_KEY:
            return False
        placeholders = ["placeholder", "your_openrouter", "sk-or-"]
        return not any(p in self.OPENROUTER_API_KEY.lower() for p in ["placeholder", "your_openrouter"])


settings = Settings()
