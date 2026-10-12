
import asyncio
import json
import logging
import re

import websockets
from websockets.exceptions import ConnectionClosed

TCP_HOST = "127.0.0.1"
TCP_PORT = 5555

WS_HOST = "127.0.0.1"
WS_PORT = 8765

MAX_USERNAME_LENGTH = 24
MAX_MESSAGE_LENGTH = 2000
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,24}$")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cloudchat-gateway")


async def handler(websocket):
    tcp_writer = None
    tcp_reader = None
    tasks = []
    username = "unknown"

    try:
        # The browser must send its username first.
        try:
            raw_username = await asyncio.wait_for(
                websocket.recv(),
                timeout=10,
            )
        except asyncio.TimeoutError:
            logger.warning("Connection timed out before username was received")
            await websocket.close(code=1008, reason="Username required")
            return

        if not isinstance(raw_username, str):
            await websocket.close(code=1008, reason="Invalid username")
            return

        username = raw_username.strip()

        # Reject empty, oversized, or malformed usernames.
        if (
            len(username) > MAX_USERNAME_LENGTH
            or not USERNAME_PATTERN.fullmatch(username)
        ):
            logger.warning("Rejected invalid username: %r", username)
            await websocket.close(code=1008, reason="Invalid username")
            return

        # Open one persistent TCP connection for this browser session.
        tcp_reader, tcp_writer = await asyncio.open_connection(
            TCP_HOST,
            TCP_PORT,
        )

        tcp_writer.write((username + "\n").encode("utf-8"))
        await tcp_writer.drain()

        logger.info("Browser connected as %s", username)

        async def tcp_to_browser():
            while True:
                line = await tcp_reader.readline()

                if not line:
                    break

                try:
                    event = json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    event = {
                        "type": "system",
                        "message": line.decode(
                            "utf-8",
                            errors="replace",
                        ).strip(),
                    }

                await websocket.send(json.dumps(event))

        async def browser_to_tcp():
            async for raw_message in websocket:
                try:
                    payload = json.loads(raw_message)
                except (json.JSONDecodeError, TypeError):
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Invalid message format.",
                    }))
                    continue

                if not isinstance(payload, dict):
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Invalid message format.",
                    }))
                    continue

                message_type = payload.get("type")

                if message_type == "chat":
                    message = str(payload.get("message", "")).strip()

                    if not message:
                        continue

                    if len(message) > MAX_MESSAGE_LENGTH:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": (
                                "Messages must be 2000 characters "
                                "or fewer."
                            ),
                        }))
                        continue

                    # The TCP server expects one message per line.
                    if "\n" in message or "\r" in message:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": (
                                "Multiline messages are not "
                                "supported yet."
                            ),
                        }))
                        continue

                    tcp_writer.write((message + "\n").encode("utf-8"))
                    await tcp_writer.drain()

                elif message_type == "command":
                    command = str(payload.get("command", "")).strip()

                    if (
                        not command
                        or "\n" in command
                        or "\r" in command
                    ):
                        continue

                    tcp_writer.write((command + "\n").encode("utf-8"))
                    await tcp_writer.drain()

                else:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Unsupported event type.",
                    }))

        tasks = [
            asyncio.create_task(tcp_to_browser()),
            asyncio.create_task(browser_to_tcp()),
        ]

        # Close the session when either direction finishes.
        _, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

        await asyncio.gather(*pending, return_exceptions=True)

    except ConnectionClosed:
        logger.info("Browser disconnected: %s", username)

    except (ConnectionError, OSError) as exc:
        logger.warning(
            "Connection error for %s: %s",
            username,
            exc,
        )

        try:
            await websocket.send(json.dumps({
                "type": "error",
                "message": "Could not connect to the chat server.",
            }))
        except (ConnectionClosed, OSError):
            pass

    except Exception:
        logger.exception(
            "Unexpected gateway error for %s",
            username,
        )

    finally:
        # Stop any remaining forwarding tasks.
        for task in tasks:
            if not task.done():
                task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Close the TCP connection cleanly.
        if tcp_writer is not None:
            tcp_writer.close()

            try:
                await tcp_writer.wait_closed()
            except (ConnectionError, OSError):
                pass

        logger.info("WebSocket session closed: %s", username)


async def main():
    logger.info(
        "CloudChat gateway starting on ws://%s:%s",
        WS_HOST,
        WS_PORT,
    )

    async with websockets.serve(
        handler,
        WS_HOST,
        WS_PORT,
        max_size=64 * 1024,
        ping_interval=20,
        ping_timeout=20,
    ):
        logger.info("CloudChat gateway is ready")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Gateway stopped")
