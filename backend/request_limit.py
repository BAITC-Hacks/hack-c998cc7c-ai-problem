"""Bound request bodies before multipart spooling, including chunked uploads."""

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
import config


class RequestLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = (
            config.MAX_UPLOAD_BYTES + 1024 * 1024
            if scope["path"] == "/api/upload"
            else 16 * 1024 * 1024
        )
        headers = dict(scope["headers"])
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid Content-Length"}, 400)(
                scope, receive, send
            )
        if length > limit:
            return await JSONResponse({"detail": "Request body too large"}, 413)(
                scope, receive, send
            )
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > limit:
                raise HTTPException(413, "Request body too large")
            return message

        await self.app(scope, bounded_receive, send)
