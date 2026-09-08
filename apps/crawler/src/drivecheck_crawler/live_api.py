from __future__ import annotations

import logging
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from drivecheck_crawler.live_search import run_live_search

log = logging.getLogger(__name__)


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


async def live_search(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Neplatný JSON"}, status_code=400)

    make = str(body.get("make") or "").strip()
    model = str(body.get("model") or "").strip()
    if not make or not model:
        return JSONResponse({"error": "Vyžadována značka a model"}, status_code=400)

    year_raw = body.get("year")
    year = int(year_raw) if year_raw is not None and str(year_raw).isdigit() else None
    limit = int(body.get("limit") or 40)
    sources = body.get("sources")
    if not isinstance(sources, list):
        sources = ["sauto", "bazos"]
    fuel = str(body.get("fuel") or "").strip() or None
    transmission = str(body.get("transmission") or "").strip() or None

    try:
        offers = run_live_search(
            make=make,
            model=model,
            year=year,
            limit=min(max(limit, 1), 80),
            sources=[str(s) for s in sources],
            fuel=fuel,
            transmission=transmission,
        )
    except Exception as exc:
        log.exception("live search failed")
        return JSONResponse({"error": str(exc), "offers": []}, status_code=502)

    return JSONResponse({"offers": offers, "count": len(offers)})


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/live-search", live_search, methods=["POST"]),
        ]
    )


app = create_app()


def serve(host: str = "0.0.0.0", port: int = 8090) -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host=host, port=port, log_level="info")
