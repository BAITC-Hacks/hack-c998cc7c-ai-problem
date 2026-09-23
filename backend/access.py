"""Shared-password protection for a single-workspace demonstration over HTTPS."""

import base64
import binascii
import secrets
import time
from collections import OrderedDict
from starlette.responses import JSONResponse, RedirectResponse
import config


class SharedPasswordAuth:
    def __init__(self, app):
        self.app = app
        self.failures = OrderedDict()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/healthz":
            return await self.app(scope, receive, send)
        password = config.APP_AUTH_PASSWORD
        if config.PUBLIC_MODE and len(password) < 16:
            return await JSONResponse({"detail": "Public access is not configured"}, 503)(scope, receive, send)
        if config.PUBLIC_MODE and scope.get("scheme") != "https":
            host = dict(scope["headers"]).get(b"host", b"").decode("latin-1")
            path = scope.get("raw_path", b"/").decode("ascii")
            query = scope.get("query_string", b"").decode("ascii")
            target = f"https://{host}{path}" + (f"?{query}" if query else "")
            return await RedirectResponse(target, status_code=307)(scope, receive, send)
        if password:
            value = dict(scope["headers"]).get(b"authorization", b"")
            valid = False
            try:
                scheme, encoded = value.split(b" ", 1)
                if scheme.lower() == b"basic":
                    username, supplied = base64.b64decode(encoded, validate=True).split(b":", 1)
                    valid = secrets.compare_digest(username, config.APP_AUTH_USER.encode()) & secrets.compare_digest(supplied, password.encode())
            except (ValueError, binascii.Error):
                pass
            if not valid:
                now = time.monotonic()
                key = (scope.get("client") or ("unknown",))[0]
                count, start = self.failures.get(key, (0, now))
                if now - start >= 60:
                    count, start = 0, now
                # Only failed supplied credentials count, not the browser's initial challenge.
                if value:
                    count += 1
                    self.failures[key] = (count, start)
                    self.failures.move_to_end(key)
                while len(self.failures) > 1024:
                    self.failures.popitem(last=False)
                if count > 20:
                    return await JSONResponse({"detail": "Too many sign-in attempts"}, 429, headers={"Retry-After": "60", "Cache-Control": "no-store"})(scope, receive, send)
                return await JSONResponse(
                    {"detail": "Sign in to this workspace"}, 401,
                    headers={"WWW-Authenticate": 'Basic realm="Khattama AI", charset="UTF-8"', "Cache-Control": "no-store"},
                )(scope, receive, send)
            self.failures.pop((scope.get("client") or ("unknown",))[0], None)

        async def private_send(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = [(k, v) for k, v in message["headers"] if k.lower() != b"cache-control"]
                message["headers"].append((b"cache-control", b"no-store"))
                if config.PUBLIC_MODE:
                    message["headers"].append((b"strict-transport-security", b"max-age=86400"))
            await send(message)

        await self.app(scope, receive, private_send)
