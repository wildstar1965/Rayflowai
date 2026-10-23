"""Bound incoming request bodies before multipart parsing consumes disk space."""
from starlette.responses import JSONResponse


class BodyTooLarge(Exception):
    pass


class RequestSizeLimit:
    def __init__(self, app, limit):
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        try:
            length = int(headers.get(b'content-length', b'0'))
            if length < 0:
                raise ValueError()
        except ValueError:
            return await JSONResponse({'detail': 'Invalid Content-Length.'}, status_code=400)(scope, receive, send)
        response = JSONResponse({'detail': 'Request exceeds MAX_REQUEST_MB. Upload fewer or smaller files.'}, status_code=413)
        if length > self.limit:
            return await response(scope, receive, send)
        received = 0
        oversized = False
        response_started = False

        async def bounded_receive():
            nonlocal received, oversized
            message = await receive()
            received += len(message.get('body', b''))
            if received > self.limit:
                oversized = True
                raise BodyTooLarge()
            return message

        async def bounded_send(message):
            nonlocal response_started
            # Multipart parsers may catch the receive exception as HTTP 400.
            # Replace that response with 413, without forwarding its body.
            if oversized:
                if not response_started:
                    response_started = True
                    await response(scope, receive, send)
                return
            if message['type'] == 'http.response.start':
                response_started = True
            await send(message)

        try:
            await self.app(scope, bounded_receive, bounded_send)
        except BodyTooLarge:
            if not response_started:
                await response(scope, receive, send)
