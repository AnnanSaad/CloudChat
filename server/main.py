import json
import re
import socket
import threading
from datetime import datetime

HOST = "127.0.0.1"
PORT = 5555

# Connected socket -> username
clients = {}

# Room name -> set of connected sockets
rooms = {"general": set()}

lock = threading.RLock()

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,24}$")
ROOM_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,30}$")
MAX_MESSAGE_LENGTH = 2000


def timestamp():
    return datetime.now().strftime("%H:%M:%S")


def make_event(event_type, **fields):
    return {
        "type": event_type,
        **fields,
        "timestamp": timestamp(),
    }


def system_message(message):
    return make_event("system", message=message)


def send_message(client, data):
    """Send a newline-delimited JSON event to a TCP client."""
    try:
        payload = json.dumps(data, ensure_ascii=False) + "\n"
        client.sendall(payload.encode("utf-8"))
        return True
    except (OSError, ConnectionError):
        return False


def get_online_users():
    with lock:
        return sorted(clients.values(), key=str.lower)


def get_available_rooms():
    with lock:
        return sorted(rooms.keys())


def broadcast(data, room="general", exclude=None):
    """Broadcast an event to a room, optionally excluding one socket."""
    with lock:
        recipients = list(rooms.get(room, set()))

    for client in recipients:
        if client is not exclude:
            send_message(client, data)


def broadcast_all(data):
    with lock:
        recipients = list(clients.keys())

    for client in recipients:
        send_message(client, data)


def broadcast_user_list():
    users = get_online_users()

    broadcast_all(
        make_event(
            "users",
            users=users,
            count=len(users),
        )
    )


def broadcast_room_list():
    broadcast_all(
        make_event(
            "rooms",
            rooms=get_available_rooms(),
        )
    )


def find_client_by_username(username):
    with lock:
        for client, existing_name in clients.items():
            if existing_name.casefold() == username.casefold():
                return client, existing_name

    return None, None


def handle_users_command(client):
    users = get_online_users()

    send_message(
        client,
        make_event(
            "users",
            users=users,
            count=len(users),
        ),
    )


def handle_rooms_command(client):
    send_message(
        client,
        make_event(
            "rooms",
            rooms=get_available_rooms(),
        ),
    )


def handle_private_message(client, username, command):
    parts = command.split(" ", 2)

    if len(parts) < 3 or not parts[1].strip() or not parts[2].strip():
        send_message(
            client,
            system_message("Usage: /pm username message"),
        )
        return

    target_username = parts[1].strip()
    private_text = parts[2].strip()

    if len(private_text) > MAX_MESSAGE_LENGTH:
        send_message(
            client,
            system_message(
                f"Private messages must be {MAX_MESSAGE_LENGTH} "
                "characters or fewer."
            ),
        )
        return

    target_client, actual_target_name = find_client_by_username(
        target_username
    )

    if target_client is None:
        send_message(
            client,
            system_message(f"User not found: {target_username}"),
        )
        return

    if target_client is client:
        send_message(
            client,
            system_message("You cannot send a private message to yourself."),
        )
        return

    delivered = send_message(
        target_client,
        make_event(
            "private",
            username=username,
            recipient=actual_target_name,
            message=private_text,
        ),
    )

    if delivered:
        send_message(
            client,
            system_message(f"Private message sent to {actual_target_name}"),
        )

        print(
            f"[PRIVATE] {username} -> "
            f"{actual_target_name}: {private_text}"
        )
    else:
        send_message(
            client,
            system_message("Could not deliver the private message."),
        )


def handle_join_command(client, username, command, current_room):
    parts = command.split(" ", 1)

    if len(parts) < 2 or not parts[1].strip():
        send_message(client, system_message("Usage: /join room-name"))
        return current_room

    new_room = parts[1].strip()

    if not ROOM_PATTERN.fullmatch(new_room):
        send_message(
            client,
            system_message(
                "Room names must contain 1-30 letters, numbers, "
                "hyphens, or underscores."
            ),
        )
        return current_room

    new_room = new_room.lower()
    room_created = False

    with lock:
        if new_room not in rooms:
            rooms[new_room] = set()
            room_created = True

        rooms.setdefault(current_room, set()).discard(client)
        rooms[new_room].add(client)

    previous_room = current_room

    send_message(
        client,
        system_message(f"You joined room: {new_room}"),
    )

    broadcast(
        system_message(f"{username} joined #{new_room}"),
        new_room,
    )

    print(f"[ROOM] {username}: #{previous_room} -> #{new_room}")

    if room_created:
        broadcast_room_list()

    return new_room


def handle_command(client, username, command, current_room):
    """Handle one plain-text command from a connected client."""
    if command == "/users":
        handle_users_command(client)
        return current_room

    if command == "/rooms":
        handle_rooms_command(client)
        return current_room

    if command.startswith("/pm "):
        handle_private_message(client, username, command)
        return current_room

    if command == "/pm":
        send_message(
            client,
            system_message("Usage: /pm username message"),
        )
        return current_room

    if command.startswith("/join ") or command == "/join":
        return handle_join_command(
            client,
            username,
            command,
            current_room,
        )

    if command == "/help":
        send_message(
            client,
            system_message(
                "Commands: /users, /rooms, /join room-name, "
                "/pm username message, /help, /quit"
            ),
        )
        return current_room

    if command == "/quit":
        return None

    if command.startswith("/"):
        send_message(
            client,
            system_message(
                f"Unknown command: {command.split(' ', 1)[0]}. "
                "Type /help for available commands."
            ),
        )
        return current_room

    return current_room


def handle_client(client, address):
    username = None
    current_room = "general"
    reader = None
    registered = False

    try:
        reader = client.makefile("r", encoding="utf-8")

        # The first TCP line is the username handshake.
        username = reader.readline().strip()

        if not USERNAME_PATTERN.fullmatch(username):
            print(
                f"[REJECTED] Invalid username/request from "
                f"{address}: {username[:80]!r}"
            )
            return

        with lock:
            duplicate = any(
                existing.casefold() == username.casefold()
                for existing in clients.values()
            )

            if not duplicate:
                clients[client] = username
                rooms.setdefault(current_room, set()).add(client)
                registered = True

        if not registered:
            send_message(
                client,
                system_message("Username already taken!"),
            )
            return

        print(f"[CONNECTED] {username} from {address}")

        send_message(
            client,
            system_message(f"Welcome {username}!"),
        )

        broadcast(
            system_message(f"{username} joined the chat"),
            current_room,
        )

        broadcast_user_list()
        broadcast_room_list()

        for line in reader:
            message = line.strip()

            if not message:
                continue

            if len(message) > MAX_MESSAGE_LENGTH:
                send_message(
                    client,
                    system_message(
                        f"Messages must be {MAX_MESSAGE_LENGTH} "
                        "characters or fewer."
                    ),
                )
                continue

            if message.startswith("/"):
                next_room = handle_command(
                    client,
                    username,
                    message,
                    current_room,
                )

                if next_room is None:
                    break

                current_room = next_room
                continue

            event = make_event(
                "chat",
                username=username,
                message=message,
                room=current_room,
            )

            broadcast(event, current_room)

            print(f"[{current_room}] {username}: {message}")

    except (OSError, UnicodeError, ConnectionError) as error:
        print(f"[ERROR] {username or address}: {error}")

    finally:
        if registered:
            with lock:
                clients.pop(client, None)

                for room_clients in rooms.values():
                    room_clients.discard(client)

            broadcast(
                system_message(f"{username} disconnected"),
                current_room,
            )

            broadcast_user_list()

            print(f"[DISCONNECTED] {username}")

        if reader is not None:
            try:
                reader.close()
            except OSError:
                pass

        try:
            client.close()
        except OSError:
            pass


def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1,
    )

    try:
        server.bind((HOST, PORT))
        server.listen()

        print("=" * 45)
        print("          CLOUDCHAT SERVER")
        print("=" * 45)
        print(f"Running on {HOST}:{PORT}")
        print("Waiting for connections...\n")

        while True:
            client, address = server.accept()

            thread = threading.Thread(
                target=handle_client,
                args=(client, address),
                daemon=True,
            )
            thread.start()

    except KeyboardInterrupt:
        print("\nServer shutting down...")

    finally:
        server.close()


if __name__ == "__main__":
    start_server()