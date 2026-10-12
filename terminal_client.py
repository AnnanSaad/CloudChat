import json
import socket
import threading
from datetime import datetime

HOST = "127.0.0.1"
PORT = 5555

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
DIM = "\033[90m"


class CloudChatClient:
    def __init__(self):
        self.client = None
        self.running = threading.Event()
        self.send_lock = threading.Lock()
        self.username = ""
        self.current_room = "general"

    def banner(self):
        print(CYAN + BOLD)
        print("=" * 58)
        print("                     CLOUDCHAT")
        print("                TERMINAL CHAT CLIENT")
        print("=" * 58)
        print(RESET)

    def show_help(self):
        print(CYAN + BOLD + "\nCOMMAND REFERENCE" + RESET)
        print("-" * 45)
        print("  /help                 Show commands")
        print("  /users                List online users")
        print("  /rooms                List available rooms")
        print("  /join <room>          Join or create a room")
        print("  /pm <user> <message>  Send a private message")
        print("  /quit                 Disconnect and exit")
        print("-" * 45)
        print("  Any other text is sent to the current room.\n")

    def send_line(self, text):
        """Send one newline-terminated protocol message."""
        if not self.running.is_set():
            return

        try:
            with self.send_lock:
                self.client.sendall(
                    (text + "\n").encode("utf-8")
                )
        except OSError:
            print(RED + "\nConnection lost." + RESET)
            self.running.clear()

    def receive_messages(self):
        """Read newline-delimited JSON events from the server."""
        buffer = b""

        try:
            while self.running.is_set():
                chunk = self.client.recv(4096)

                if not chunk:
                    break

                buffer += chunk

                while b"\n" in buffer:
                    raw_line, buffer = buffer.split(b"\n", 1)

                    if not raw_line.strip():
                        continue

                    try:
                        event = json.loads(
                            raw_line.decode("utf-8")
                        )
                        self.display_event(event)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        print(
                            YELLOW
                            + "\nReceived an unrecognized server event."
                            + RESET
                        )

        except OSError:
            pass

        finally:
            self.running.clear()

            if self.client:
                try:
                    self.client.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def display_event(self, event):
        """Format server events for terminal display."""
        event_type = event.get("type", "unknown")
        timestamp = event.get("timestamp", "")

        if timestamp:
            time_label = f"{DIM}[{timestamp}]{RESET} "
        else:
            time_label = ""

        if event_type == "system":
            message = event.get("message", "")
            print(
                f"\n{time_label}{YELLOW}[SYSTEM]{RESET} {message}"
            )

            if message.startswith("You joined room:"):
                self.current_room = message.split(":", 1)[1].strip()

        elif event_type == "chat":
            username = event.get("username", "Unknown")
            message = event.get("message", "")
            room = event.get("room", self.current_room)

            print(
                f"\n{time_label}"
                f"{MAGENTA}#{room}{RESET} "
                f"{GREEN}{username}{RESET}: {message}"
            )

        elif event_type == "private":
            sender = event.get("username", "Unknown")
            recipient = event.get("recipient", "")
            message = event.get("message", "")

            if sender.lower() == self.username.lower():
                label = f"DM to {recipient}"
            else:
                label = f"DM from {sender}"

            print(
                f"\n{time_label}"
                f"{CYAN}[PRIVATE: {label}]{RESET} {message}"
            )

        elif event_type == "users":
            users = event.get("users", [])
            count = event.get("count", len(users))

            print(
                f"\n{CYAN}{BOLD}ONLINE USERS ({count}){RESET}"
            )

            if users:
                for user in users:
                    marker = (
                        " (you)"
                        if user.lower() == self.username.lower()
                        else ""
                    )
                    print(f"  • {user}{marker}")
            else:
                print("  No users online.")

        elif event_type == "rooms":
            rooms = event.get("rooms", [])

            print(f"\n{CYAN}{BOLD}AVAILABLE ROOMS{RESET}")

            for room in rooms:
                marker = "  ← current" if room == self.current_room else ""
                print(f"  • #{room}{marker}")

        else:
            print(f"\n{time_label}{event}")

        print(f"{BOLD}#{self.current_room}>{RESET} ", end="", flush=True)

    def connect(self):
        self.banner()

        print("Connect to your local CloudChat TCP server.\n")

        self.username = input("Enter username: ").strip()

        if not self.username:
            print(RED + "Username cannot be empty." + RESET)
            return False

        if len(self.username) > 24:
            print(RED + "Username must be 24 characters or fewer." + RESET)
            return False

        try:
            self.client = socket.create_connection(
                (HOST, PORT),
                timeout=5,
            )
            self.client.settimeout(None)

            # The server expects the username as its first line.
            self.client.sendall(
                (self.username + "\n").encode("utf-8")
            )

            self.running.set()

            receiver = threading.Thread(
                target=self.receive_messages,
                daemon=True,
            )
            receiver.start()

            print(
                GREEN
                + f"\nConnected to CloudChat as {self.username}!"
                + RESET
            )

            self.show_help()
            return True

        except (OSError, ConnectionError) as error:
            print(RED + f"\nCould not connect: {error}" + RESET)
            print("Make sure the TCP server is running:")
            print("  py server/main.py")
            return False

    def run(self):
        if not self.connect():
            return

        try:
            while self.running.is_set():
                try:
                    text = input(
                        f"{BOLD}#{self.current_room}>{RESET} "
                    ).strip()
                except EOFError:
                    break

                if not text:
                    continue

                if text == "/help":
                    self.show_help()

                elif text == "/quit":
                    self.send_line("/quit")
                    break

                else:
                    self.send_line(text)

        except KeyboardInterrupt:
            print("\nLeaving CloudChat...")

        finally:
            self.running.clear()

            if self.client:
                try:
                    self.client.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

                try:
                    self.client.close()
                except OSError:
                    pass

            print(GREEN + "\nDisconnected from CloudChat." + RESET)


if __name__ == "__main__":
    CloudChatClient().run()