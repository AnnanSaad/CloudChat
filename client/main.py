import socket
import threading
import json

HOST = "127.0.0.1"
PORT = 5555


def receive_messages(client):
    try:
        reader = client.makefile(
            "r", encoding="utf-8"
        )

        for line in reader:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            message_type = data.get("type")

            if message_type == "chat":
                username = data.get("username")
                message = data.get("message")
                timestamp = data.get("timestamp")

                print(
                    f"\n[{timestamp}] "
                    f"{username}: {message}"
                )

            elif message_type == "system":
                print(
                    f"\n[SYSTEM] {data.get('message')}"
                )
            elif message_type == "private":
                print(
                     f"\n[PRIVATE] {data.get('username')}: "
                     f"{data.get('message')}"
                )
            elif message_type == "error":
                print(
                    f"\n[ERROR] {data.get('message')}"
                )
                break

    except OSError:
        pass

    finally:
        print("\nDisconnected from server.")


def start_client():
    username = input("Enter your username: ").strip()

    if not username:
        print("Username cannot be empty.")
        return

    client = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    try:
        client.connect((HOST, PORT))

    except ConnectionRefusedError:
        print("Server is not running.")
        return

    client.sendall(
        (username + "\n").encode("utf-8")
    )

    thread = threading.Thread(
        target=receive_messages,
        args=(client,),
        daemon=True
    )

    thread.start()

    print("\nConnected to CloudChat!")
    print("Type /quit to leave.\n")

    try:
        while True:
            message = input()

            if not message:
                continue

            client.sendall(
                (message + "\n").encode("utf-8")
            )

            if message == "/quit":
                break

    except (KeyboardInterrupt, OSError):
        pass

    finally:
        client.close()


if __name__ == "__main__":
    start_client()