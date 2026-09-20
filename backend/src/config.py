"""Configuration and settings module for Nivaran AI Backend."""

import os
from dotenv import load_dotenv, find_dotenv

# Load environment variables from backend/.env or root .env
_backend_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.path.exists(_backend_env):
    load_dotenv(_backend_env)
else:
    load_dotenv(find_dotenv(usecwd=True))

# --- Server & General Config ---
PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "0.0.0.0")

# --- API Keys & Credentials ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# --- Telegram & Messaging Config ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "NivaranAiSupportBot")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
TELEGRAM_MODE = os.getenv("TELEGRAM_MODE", "polling").lower()  # "polling" or "webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

# --- SMTP Email Configuration ---
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "") or SMTP_USER


# --- Database & Supabase Config ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")

# --- RAG & AI Model Configuration ---
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

# --- Conversational Memory Window ---
# Configurable window size for fetching previous messages for short-term chat context
CHAT_HISTORY_WINDOW = 5  # Exposed constant (range 5-10 recommended)

# --- Escalation & Confidence Thresholds ---
# TODO: Team input needed — tune SIMILARITY_THRESHOLD based on production knowledge precision
SIMILARITY_THRESHOLD = 0.5

# TODO: Team input needed — adjust LOW_CONFIDENCE_THRESHOLD for automatic ticket generation
LOW_CONFIDENCE_THRESHOLD = 0.45

# TODO: Team input needed — confirm consecutive unhelpful responses before escalation trigger
REPEATED_UNRESOLVED_THRESHOLD = 3
