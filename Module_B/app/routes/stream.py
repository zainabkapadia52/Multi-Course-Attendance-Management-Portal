import time
from flask import Blueprint, Response, stream_with_context, request
from ..events import subscribe, unsubscribe
from ..auth import verify_session, AuthError

bp = Blueprint("stream", __name__)

@bp.get("/stream")
def sse_stream():
    # Validate session before opening stream
    session_id = request.cookies.get("session_id")
    mac        = request.cookies.get("session_mac")
    try:
        verify_session(session_id, mac)
    except AuthError:
        return {"error": "Unauthorized"}, 401

    q = subscribe()

    def generate():
        # Send a heartbeat immediately so browser confirms connection
        yield "event: connected\ndata: {}\n\n"
        try:
            while True:
                try:
                    payload = q.get(timeout=25)
                    yield f"data: {payload}\n\n"
                except Exception:
                    # Heartbeat every 25s to keep connection alive
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            unsubscribe(q)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",   # important for nginx
            "Connection":        "keep-alive",
        }
    )