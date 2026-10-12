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

# Accept ordinary usernames, not HTTP request lines or header values.
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,24}$")


def timestamp():
    return datetime.now().strftime("%H:%M:%S")


def send_message(client, data):
    """Send one JSON event to a client."""
    try:
        payload = json.dumps(data) + "\n"
        client.sendall(payload.encode("utf-8"))
        return True
    except (OSError, ConnectionError):
        return False


def system_message(message):
    return {
        "type": "system",
        "message": message,
        "timestamp": timestamp(),
    }


def get_online_users():
    """Return a snapshot of connected usernames."""
    with lock:
        return sorted(clients.values(), key=str.lower)


def broadcast(data, room="general"):
    """Broadcast an event to everyone in a room."""
    with lock:
        recipients = list(rooms.get(room, set()))

    for client in recipients:
        send_message(client, data)


def broadcast_all(data):
    """Broadcast an event to every connected client."""
    with lock:
        recipients = list(clients.keys())

    for client in recipients:
        send_message(client, data)


def broadcast_user_list():
    """Synchronize the online-user list across all clients."""
    users = get_online_users()

    event = {
        "type": "users",
        "users": users,
        "count": len(users),
        "timestamp": timestamp(),
    }

    broadcast_all(event)


def broadcast_room_list():
    """Synchronize available rooms across all connected clients."""
    with lock:
        available_rooms = sorted(rooms.keys())

    event = {
        "type": "rooms",
        "rooms": available_rooms,
        "timestamp": timestamp(),
    }

    broadcast_all(event)


def handle_client(client, address):
    username = None
    current_room = "general"
    reader = None
    registered = False

    try:
        reader = client.makefile("r", encoding="utf-8")

        # The first line received from a client is its username.
        username = reader.readline().strip()

        # Reject HTTP requests, header values, and malformed usernames
        # before they can be registered or broadcast to chat users.
        if not USERNAME_PATTERN.fullmatch(username):
            print(
                f"[REJECTED] Invalid username/request from "
                f"{address}: {username[:80]!r}"
            )
            return

        # Register the user and join the default room atomically.
        with lock:
            duplicate = any(
                existing.lower() == username.lower()
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

            if len(message) > 2000:
                send_message(
                    client,
                    system_message(
                        "Messages must be 2000 characters or fewer."
                    ),
                )
                continue

            # LIST ONLINE USERS
            if message == "/users":
                users = get_online_users()

                send_message(
                    client,
                    {
                        "type": "users",
                        "users": users,
                        "count": len(users),
                        "timestamp": timestamp(),
                    },
                )

            # PRIVATE MESSAGING
            elif message.startswith("/pm "):
                parts = message.split(" ", 2)

                if len(parts) < 3 or not parts[2].strip():
                    send_message(
                        client,
                        system_message(
                            "Usage: /pm username message"
                        ),
                    )
                    continue

                target_username = parts[1].strip()
                private_text = parts[2].strip()

                with lock:
                    target_client = next(
                        (
                            sock
                            for sock, name in clients.items()
                            if name.lower() == target_username.lower()
                        ),
                        None,
                    )

                    actual_target_name = (
                        clients.get(target_client)
                        if target_client is not None
                        else None
                    )

                if target_client is None:
                    send_message(
                        client,
                        system_message("User not found!"),
                    )
                    continue

                delivered = send_message(
                    target_client,
                    {
                        "type": "private",
                        "username": username,
                        "recipient": actual_target_name,
                        "message": private_text,
                        "timestamp": timestamp(),
                    },
                )

                if delivered:
                    send_message(
                        client,
                        system_message(
                            f"Private message sent to {actual_target_name}"
                        ),
                    )

                    print(
                        f"[PRIVATE] {username} -> "
                        f"{actual_target_name}: {private_text}"
                    )
                else:
                    send_message(
                        client,
                        system_message(
                            "Could not deliver the private message."
                        ),
                    )

            # JOIN CHAT ROOM
            elif message.startswith("/join "):
                new_room = message.split(" ", 1)[1].strip()

                if not new_room:
                    send_message(
                        client,
                        system_message("Room name required."),
                    )
                    continue

                if len(new_room) > 30 or not all(
                    char.isalnum() or char in "_-"
                    for char in new_room
                ):
                    send_message(
                        client,
                        system_message(
                            "Room names may contain letters, "
                            "numbers, hyphens and underscores."
                        ),
                    )
                    continue

                new_room = new_room.lower()
                room_created = False

                with lock:
                    if new_room not in rooms:
                        rooms[new_room] = set()
                        room_created = True

                    rooms[current_room].discard(client)
                    rooms[new_room].add(client)

                previous_room = current_room
                current_room = new_room

                send_message(
                    client,
                    system_message(
                        f"You joined room: {current_room}"
                    ),
                )

                broadcast(
                    system_message(
                        f"{username} joined #{current_room}"
                    ),
                    current_room,
                )

                print(
                    f"[ROOM] {username}: "
                    f"#{previous_room} -> #{current_room}"
                )

                if room_created:
                    broadcast_room_list()

            # LIST ROOMS
            elif message == "/rooms":
                with lock:
                    available_rooms = sorted(rooms.keys())

                send_message(
                    client,
                    {
                        "type": "rooms",
                        "rooms": available_rooms,
                        "timestamp": timestamp(),
                    },
                )

            # DISCONNECT
            elif message == "/quit":
                break

            # PUBLIC GROUP MESSAGING
            else:
                data = {
                    "type": "chat",
                    "username": username,
                    "message": message,
                    "room": current_room,
                    "timestamp": timestamp(),
                }

                broadcast(data, current_room)

                print(
                    f"[{current_room}] "
                    f"{username}: {message}"
                )

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
    server = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

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