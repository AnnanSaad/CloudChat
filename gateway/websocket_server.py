
import asyncio
import json
import logging
import re

import websockets
from websockets.exceptions import ConnectionClosed

TCP_HOST = "127.0.0.1"
TCP_PORT = 5555

WS_HOST = "0.0.0.0"
WS_PORT = 8765

MAX_USERNAME_LENGTH = 24
MAX_MESSAGE_LENGTH = 2000

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,24}$")
ROOM_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,30}$")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cloudchat-gateway")


def encode_event(event_type, **fields):
    return json.dumps({
        "type": event_type,
        **fields,
    })


async def send_event(websocket, event_type, **fields):
    await websocket.send(encode_event(event_type, **fields))


async def handler(websocket):
    tcp_reader = None
    tcp_writer = None
    tasks = []
    username = "unknown"

    try:
        # -----------------------------------------
        # 1. Receive and validate the username
        # -----------------------------------------
        try:
            raw_username = await asyncio.wait_for(
                websocket.recv(),
                timeout=10,
            )
        except asyncio.TimeoutError:
            await websocket.close(
                code=1008,
                reason="Username required",
            )
            return

        if not isinstance(raw_username, str):
            await websocket.close(
                code=1008,
                reason="Invalid username",
            )
            return

        username = raw_username.strip()

        if (
            len(username) > MAX_USERNAME_LENGTH
            or not USERNAME_PATTERN.fullmatch(username)
        ):
            logger.warning("Rejected invalid username: %r", username)

            await websocket.close(
                code=1008,
                reason="Invalid username",
            )
            return

        # -----------------------------------------
        # 2. Connect to the TCP chat server
        # -----------------------------------------
        tcp_reader, tcp_writer = await asyncio.open_connection(
            TCP_HOST,
            TCP_PORT,
        )

        tcp_writer.write(f"{username}\n".encode("utf-8"))
        await tcp_writer.drain()

        logger.info("Connected: %s", username)

        # -----------------------------------------
        # 3. TCP -> WebSocket
        # -----------------------------------------
        async def tcp_to_browser():
            while True:
                line = await tcp_reader.readline()

                if not line:
                    logger.info(
                        "TCP connection ended for %s",
                        username,
                    )
                    break

                try:
                    event = json.loads(line.decode("utf-8"))

                    if not isinstance(event, dict):
                        event = {
                            "type": "system",
                            "message": str(event),
                        }

                except (json.JSONDecodeError, UnicodeDecodeError):
                    event = {
                        "type": "system",
                        "message": line.decode(
                            "utf-8",
                            errors="replace",
                        ).strip(),
                    }

                await websocket.send(
                    json.dumps(event, ensure_ascii=False)
                )

        # -----------------------------------------
        # 4. WebSocket -> TCP
        # -----------------------------------------
        async def browser_to_tcp():
            async for raw_message in websocket:
                try:
                    payload = json.loads(raw_message)

                except (json.JSONDecodeError, TypeError):
                    await send_event(
                        websocket,
                        "error",
                        message="Invalid message format.",
                    )
                    continue

                if not isinstance(payload, dict):
                    await send_event(
                        websocket,
                        "error",
                        message="Message must be a JSON object.",
                    )
                    continue

                message_type = payload.get("type")

                # -----------------------------
                # Public chat message
                # -----------------------------
                if message_type == "chat":
                    raw_text = payload.get("message", "")

                    if not isinstance(raw_text, str):
                        await send_event(
                            websocket,
                            "error",
                            message="Message must be text.",
                        )
                        continue

                    message = raw_text.strip()

                    if not message:
                        continue

                    if len(message) > MAX_MESSAGE_LENGTH:
                        await send_event(
                            websocket,
                            "error",
                            message=(
                                "Messages must be 2000 characters "
                                "or fewer."
                            ),
                        )
                        continue

                    if "\n" in message or "\r" in message:
                        await send_event(
                            websocket,
                            "error",
                            message="Multiline messages are not supported.",
                        )
                        continue

                    # Route slash-prefixed input as a command too.
                    # This protects against clients that accidentally
                    # send /users as a chat event.
                    if message.startswith("/"):
                        command = message
                    else:
                        command = None

                    tcp_writer.write(
                        f"{command or message}\n".encode("utf-8")
                    )
                    await tcp_writer.drain()

                # -----------------------------
                # Explicit slash command
                # -----------------------------
                elif message_type == "command":
                    raw_command = payload.get("command", "")

                    if not isinstance(raw_command, str):
                        await send_event(
                            websocket,
                            "error",
                            message="Command must be text.",
                        )
                        continue

                    command = raw_command.strip()

                    if not command:
                        continue

                    if "\n" in command or "\r" in command:
                        await send_event(
                            websocket,
                            "error",
                            message="Commands must be a single line.",
                        )
                        continue

                    if len(command) > MAX_MESSAGE_LENGTH:
                        await send_event(
                            websocket,
                            "error",
                            message="Command is too long.",
                        )
                        continue

                    if not command.startswith("/"):
                        await send_event(
                            websocket,
                            "error",
                            message="Commands must start with /.",
                        )
                        continue

                    # Validate room names before forwarding joins.
                    if command.startswith("/join"):
                        parts = command.split(maxsplit=1)

                        if len(parts) != 2:
                            await send_event(
                                websocket,
                                "error",
                                message="Usage: /join room-name",
                            )
                            continue

                        if not ROOM_PATTERN.fullmatch(parts[1]):
                            await send_event(
                                websocket,
                                "error",
                                message="Invalid room name.",
                            )
                            continue

                    tcp_writer.write(
                        f"{command}\n".encode("utf-8")
                    )
                    await tcp_writer.drain()

                else:
                    await send_event(
                        websocket,
                        "error",
                        message="Unsupported event type.",
                    )

        # -----------------------------------------
        # 5. Run both forwarding tasks
        # -----------------------------------------
        tasks = [
            asyncio.create_task(
                tcp_to_browser(),
                name=f"tcp-to-browser-{username}",
            ),
            asyncio.create_task(
                browser_to_tcp(),
                name=f"browser-to-tcp-{username}",
            ),
        ]

        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Surface unexpected task failures for diagnostics.
        for task in done:
            if task.cancelled():
                continue

            error = task.exception()

            if error is not None:
                if isinstance(error, ConnectionClosed):
                    logger.info(
                        "WebSocket closed for %s",
                        username,
                    )
                else:
                    logger.error(
                        "Forwarding task failed for %s: %s",
                        username,
                        error,
                    )

        for task in pending:
            task.cancel()

        await asyncio.gather(
            *pending,
            return_exceptions=True,
        )

    except ConnectionClosed:
        logger.info("Browser disconnected: %s", username)

    except (ConnectionError, OSError) as exc:
        logger.warning(
            "Connection error for %s: %s",
            username,
            exc,
        )

        try:
            await send_event(
                websocket,
                "error",
                message="Could not connect to the chat server.",
            )
        except (ConnectionClosed, OSError):
            pass

    except asyncio.CancelledError:
        raise

    except Exception:
        logger.exception(
            "Unexpected gateway error for %s",
            username,
        )

    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

        if tcp_writer is not None:
            tcp_writer.close()

            try:
                await tcp_writer.wait_closed()
            except (ConnectionError, OSError):
                pass

        logger.info("Session closed: %s", username)


async def main():
    logger.info(
        "Starting CloudChat gateway on %s:%s",
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
