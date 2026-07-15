"""
Health check endpoint.
"""
import time
import os
from aiohttp import web

START_TIME = time.time()


async def health_handler(request: web.Request) -> web.Response:
    checks = {}
    healthy = True

    try:
        import sqlite3
        from db import DB
        conn = sqlite3.connect(DB, timeout=5)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        checks["database"] = "ok" if integrity == "ok" else "error"
        if integrity != "ok":
            healthy = False
    except Exception as e:
        checks["database"] = str(e)
        healthy = False

    checks["uptime_seconds"] = int(time.time() - START_TIME)

    try:
        st = os.statvfs(".")
        free_gb = (st.f_bavail * st.f_frsize) / (1024**3)
        checks["disk_free_gb"] = round(free_gb, 2)
        if free_gb < 1:
            healthy = False
    except Exception:
        pass

    try:
        commit = os.popen("git rev-parse --short HEAD 2>/dev/null").read().strip()
        checks["version"] = commit or "unknown"
    except Exception:
        checks["version"] = "unknown"

    return web.json_response(
        {"status": "healthy" if healthy else "unhealthy", "checks": checks},
        status=200 if healthy else 503,
    )
