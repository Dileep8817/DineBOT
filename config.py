# Shared config: rate limiter (SlowAPI) for use in main and routers

import os
from pathlib import Path

from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address

# Project root (parent of this file) so datafiles and .env resolve when cwd is elsewhere
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

_data_dir_env = os.getenv("DATA_DIR", "").strip()
if _data_dir_env:
    DATA_DIR = Path(_data_dir_env).expanduser().resolve()
else:
    DATA_DIR = PROJECT_ROOT / "data"

_default_limit = os.getenv("RATE_LIMIT_DEFAULT", "100/minute")
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_default_limit],
)
