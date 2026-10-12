import asyncio
import logging
import os
import threading

import websockets

from server.main import start_server
from gateway.websocket_server import handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cloudchat-deployment")


def run_tcp_server():
    """Run the existing TCP server in a background thread."""
    start_server()


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
    import time
    time.sleep(1)

    asyncio.run(run_websocket_gateway())


if __name__ == "__main__":
    main()