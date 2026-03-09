# Shared config: rate limiter (SlowAPI) for use in main and routers

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],  # global; stricter limits applied per-route (e.g. /chat)
)
