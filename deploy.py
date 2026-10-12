import asyncio
import logging
import os
import threading
import time

import websockets
from websockets.http11 import Response
from websockets.datastructures import Headers

from server.main import start_server
from gateway.websocket_server import handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cloudchat-deployment")


def run_tcp_server():
    """Run the existing TCP server in a background thread."""
    start_server()


def process_request(connection, request):
    """Handle ordinary HTTP health-check requests."""
    if request.path == "/health":
        return Response(
            status_code=200,
            reason_phrase="OK",
            headers=Headers(
                [
                    ("Content-Type", "text/plain; charset=utf-8"),
                    ("Cache-Control", "no-cache"),
                ]
            ),
            body=b"CloudChat is healthy\n",
        )

    return None


async def run_websocket_gateway():
    """Expose the WebSocket gateway on Render's public port."""
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "8765"))

    logger.info("Starting WebSocket gateway on %s:%s", host, port)

    async with websockets.serve(
        handler,
        host,
        port,
        max_size=64 * 1024,
        ping_interval=20,
        ping_timeout=20,
        process_request=process_request,
    ):
        logger.info("CloudChat gateway is ready.")
        await asyncio.Future()


def main():
    tcp_thread = threading.Thread(
        target=run_tcp_server,
        daemon=True,
        name="cloudchat-tcp-server",
    )
    tcp_thread.start()

    # Allow the TCP server a moment to start listening.
    time.sleep(1)

    asyncio.run(run_websocket_gateway())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("CloudChat deployment stopped.")
