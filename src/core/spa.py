"""Serves the built React SPA (ui/dist) at the root, on the same port as the API."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException


def mount_spa(app: FastAPI, dist_dir: Path) -> None:
    """Mount the SPA at "/", guarded on the build existing so the backend
    (and tests) run without a compiled frontend. Call this last: the mount
    catches everything not claimed by an earlier route, so the API routers
    (/chat, /agent) and the docs routes (/docs, /openapi.json) must already be
    registered on `app` or this mount will shadow them."""

    if not dist_dir.is_dir():
        return
    app.mount("/", _SpaStaticFiles(directory=dist_dir, html=True), name="ui")


class _SpaStaticFiles(StaticFiles):
    """No-cache headers (so browsers don't keep stale modules across deploys)
    plus an index.html fallback so client-side routes survive a browser
    refresh."""

    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
            if response.status_code == 404:
                response = await super().get_response("index.html", scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            response = await super().get_response("index.html", scope)
        response.headers["Cache-Control"] = "no-cache"
        return response
