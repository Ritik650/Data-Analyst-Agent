"""Vercel serverless entrypoint — exposes the FastAPI ASGI app."""
import os
import sys

# Make repo-root imports (config, api.*) resolvable inside the Vercel bundle.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.main import app  # noqa: E402,F401  (Vercel detects the ASGI `app`)
