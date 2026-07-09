"""WebRTC proxy to comma 4's webrtcd server.

Relays SDP offers from the browser to the comma 4's WebRTC server (port 5001)
and returns the SDP answer. This enables the browser to establish a direct
WebRTC connection to the comma 4 for camera video + cereal data.

Pattern from: openpilot/tools/bodyteleop/web.py
"""

import logging

import aiohttp
from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from src.config import load_config

logger = logging.getLogger(__name__)

comma_router = APIRouter(prefix="/api/comma")


@comma_router.post("/offer")
async def comma_offer(request: Request):
    """Relay WebRTC offer to comma 4's webrtcd and return the answer."""
    config = load_config()
    body = await request.json()

    sdp = body.get("sdp")
    if not sdp:
        return JSONResponse({"error": "missing sdp"}, status_code=400)

    stream_body = {
        "sdp": sdp,
        "cameras": config.comma.cameras,
        "bridge_services_in": [],
        "bridge_services_out": config.comma.services,
    }

    webrtcd_url = f"http://{config.comma.host}:{config.comma.port}/stream"
    logger.info(f"Forwarding WebRTC offer to {webrtcd_url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(webrtcd_url, json=stream_body, timeout=10) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"webrtcd returned {resp.status}: {error_text}")
                    return JSONResponse(
                        {"error": f"comma 4 returned {resp.status}"},
                        status_code=502,
                    )
                answer = await resp.json()
                return JSONResponse(answer)
    except aiohttp.ClientError as e:
        logger.warning(f"Cannot reach comma 4 at {webrtcd_url}: {e}")
        return JSONResponse(
            {"error": "comma 4 unreachable", "detail": str(e)},
            status_code=503,
        )


@comma_router.get("/status")
async def comma_status():
    """Check if comma 4 is reachable."""
    config = load_config()
    webrtcd_url = f"http://{config.comma.host}:{config.comma.port}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(webrtcd_url, timeout=3) as resp:
                return {"connected": True, "status": resp.status}
    except aiohttp.ClientError:
        return {"connected": False, "status": None}
