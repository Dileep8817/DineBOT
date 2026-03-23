# Shared config: rate limiter (SlowAPI) for use in main and routers

from pathlib import Path

from slowapi import Limiter
from slowapi.util import get_remote_address

# Project root (parent of this file) so data files resolve when cwd is not the project dir
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],  # global; stricter limits applied per-route (e.g. /chat)
)
