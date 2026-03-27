# Shared config: rate limiter (SlowAPI) for use in main and routers

from pathlib import Path

from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address

# Project root (parent of this file) so datafiles and .env resolve when cwd is elsewhere
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")
DATA_DIR = PROJECT_ROOT / "data"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],  # global; stricter limits applied per-route (e.g. /chat)
)
