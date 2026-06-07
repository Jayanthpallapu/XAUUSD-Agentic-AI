import os
from pathlib import Path
from dotenv import load_dotenv

# ─── Load .env from the project root ─────────────────────────────────────────
# Handles two cases:
#   1. Running from the repo root:   d:/XAUUSD Agentic Company/
#   2. Running from frontend/:       d:/XAUUSD Agentic Company/frontend/
#      (when copied there for Vercel serverless functions)
#
# Single source of truth: root .env
# Next.js mirror:         frontend/.env.local  (same content, required by Next.js)

_here = Path(__file__).resolve().parent

# Try root .env first, then one level up, then system env
for candidate in [
    _here / ".env",           # same dir as config.py
    _here.parent / ".env",    # one level up (if config.py is in frontend/)
]:
    if candidate.exists():
        load_dotenv(candidate)
        break
else:
    load_dotenv()  # fall back to system environment variables


class Settings:
    # ─── System ──────────────────────────────────────────────────────────────
    PORT: int = int(os.getenv("PORT", 3000))
    RUN_INTERVAL_MINUTES: int = int(os.getenv("RUN_INTERVAL_MINUTES", 15))
    INTERNAL_API_TOKEN: str = os.getenv("INTERNAL_API_TOKEN", "dev-token")

    # ─── LLM ─────────────────────────────────────────────────────────────────
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    # ─── Supabase ─────────────────────────────────────────────────────────────
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    # ─── Telegram ─────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # ─── Market Data APIs ─────────────────────────────────────────────────────
    ALPHA_VANTAGE_API_KEY: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    TWELVE_DATA_API_KEY: str = os.getenv("TWELVE_DATA_API_KEY", "")
    FRED_API_KEY: str = os.getenv("FRED_API_KEY", "")
    FMP_API_KEY: str = os.getenv("FMP_API_KEY", "")
    COINGECKO_API_KEY: str = os.getenv("COINGECKO_API_KEY", "")
    FINNHUB_API_KEY: str = os.getenv("FINNHUB_API_KEY", "")

    # ─── Validation helpers ───────────────────────────────────────────────────
    @property
    def is_supabase_configured(self) -> bool:
        if not self.SUPABASE_KEY:
            return False
        placeholders = ["placeholder", "paste_your", "your_supabase", "your-supabase"]
        if any(p in self.SUPABASE_KEY.lower() for p in placeholders):
            return False
        return bool(self.SUPABASE_URL)

    @property
    def is_telegram_configured(self) -> bool:
        return bool(self.TELEGRAM_BOT_TOKEN and self.TELEGRAM_CHAT_ID)

    @property
    def is_groq_configured(self) -> bool:
        return bool(self.GROQ_API_KEY and not self.GROQ_API_KEY.startswith("gsk_your"))


settings = Settings()
