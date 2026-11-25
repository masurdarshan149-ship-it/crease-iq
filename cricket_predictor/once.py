"""Load-once helper for the big data files.

`functools.lru_cache` caches the result, but if several requests arrive together at start-up (the page asks for half
a dozen things at once, plus the background warm-up) each of them starts its own load of the same models and data
files, so the PC does the work three or four times over. `locked_cache` lets the first caller load and makes the
others wait for that one result.
"""

from __future__ import annotations

import threading
from functools import lru_cache, wraps


def locked_cache(fn):
    cached = lru_cache(maxsize=1)(fn)
    lock = threading.Lock()

    @wraps(fn)
    def wrapper():
        if cached.cache_info().currsize:  # already loaded: no need to queue
            return cached()
        with lock:
            return cached()

    wrapper.cache_clear = cached.cache_clear
    wrapper.cache_info = cached.cache_info
    return wrapper
