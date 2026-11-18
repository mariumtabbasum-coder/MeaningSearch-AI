import os
from dotenv import load_dotenv
load_dotenv()
BASE = os.path.dirname(os.path.abspath(__file__))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
_DEFAULT = "gemini-flash-latest,gemini-3.8-flash,gemini-3.6-flash,gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite"
CHAT_MODELS = [m.strip() for m in os.getenv("GEMINI_CHAT_MODEL", _DEFAULT).split(",") if m.strip()]
CHAT_MODEL = CHAT_MODELS[0]
EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-2")
ON_VERCEL = bool(os.getenv("VERCEL"))
# Vercel's filesystem is read-only except /tmp
DB_PATH = "/tmp/meaningsearch.db" if ON_VERCEL else os.path.join(BASE, "data", "meaningsearch.db")
DOCS_JSON = os.path.join(BASE, "data", "documents.json")
FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "")
