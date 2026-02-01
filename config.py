"""Central configuration — everything is overridable via environment variables."""
import os

# LLM (Google Gemini — free tier at https://aistudio.google.com/apikey)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "16000"))

# Redis (local: redis://localhost:6379/0, Upstash: rediss://default:<pass>@<host>:6379)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Job / report lifecycle
REPORT_TTL_SECONDS = int(os.getenv("REPORT_TTL_SECONDS", "86400"))  # 24h
MAX_DATASET_BYTES = int(os.getenv("MAX_DATASET_BYTES", str(4 * 1024 * 1024)))  # Vercel body limit is 4.5MB

# Sandbox limits
SANDBOX_TIMEOUT_SECONDS = int(os.getenv("SANDBOX_TIMEOUT_SECONDS", "90"))
SANDBOX_MEMORY_MB = int(os.getenv("SANDBOX_MEMORY_MB", "1536"))  # RLIMIT_AS; must fit pandas+matplotlib imports
SANDBOX_CPU_SECONDS = int(os.getenv("SANDBOX_CPU_SECONDS", "60"))

# Agent loop caps
MAX_CODER_RETRIES = int(os.getenv("MAX_CODER_RETRIES", "3"))   # total attempts per plan step
MAX_CRITIC_RETRIES = int(os.getenv("MAX_CRITIC_RETRIES", "2"))  # insight regenerations on ungrounded claims
MAX_PLAN_QUESTIONS = int(os.getenv("MAX_PLAN_QUESTIONS", "5"))
