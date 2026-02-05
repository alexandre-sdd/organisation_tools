import os
from pathlib import Path

# Load `server/.env` (if present) so local dev doesn't require re-exporting env vars.
# This runs before we read OPENAI_MODEL / OPENAI_API_KEY from the environment.
try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
except Exception:
    # If python-dotenv isn't installed (or file is missing), fall back to process env.
    pass

DEFAULT_MODEL_NAME = "gpt-4o-2024-08-06"
MODEL_NAME = os.getenv("OPENAI_MODEL", DEFAULT_MODEL_NAME)
OPENAI_API_URL = "https://api.openai.com/v1/responses"
