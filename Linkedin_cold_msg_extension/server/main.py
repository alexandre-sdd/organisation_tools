"""Compatibility entrypoint for existing uvicorn commands.

You can now run either:
- uvicorn Linkedin_cold_msg_extension.server.app.main:app --reload
- uvicorn Linkedin_cold_msg_extension.server.main:app --reload
"""

from .app.main import app  # re-export
