
import os
import time

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def show_banner():
    print("=" * 58)
    print("                 CLOUDCHAT")
    print("          Terminal Experience v1.0")
    print("=" * 58)
    print("  Real-time messaging | TCP | WebSocket | React")
    print("=" * 58)


def show_guide():
    print("""
WELCOME TO CLOUDCHAT!

CloudChat is a real-time messaging platform designed for
fast communication between connected users.

FEATURES
--------
[1] Group Messaging
    Send messages to users in a shared chat room.

[2] Private Messaging
    Send direct messages to individual users.

[3] Channels
    Switch between channels such as general, developers,
    and random.

[4] Online Members
    View connected users and monitor their status.

[5] Unread Notifications
    Track unread private messages.

ARCHITECTURE
------------
Client  -->  TCP Chat Server  -->  Connected Clients
                    ^
                    |
             WebSocket Gateway
                    ^
                    |
              React Frontend

GETTING STARTED
---------------
1. Start the TCP server.
2. Start the WebSocket gateway.
3. Connect a client.
4. Join a channel and start messaging.

This guide runs entirely in your terminal.
The graphical interface is not opened automatically.
""")


def main():
    while True:
        clear_screen()
        show_banner()
        show_guide()

        print("OPTIONS")
        print("-------")
        print("[1] View startup instructions")
        print("[2] View available chat commands")
        print("[3] Launch CloudChat services")
        print("[4] Exit")

        choice = input("\nSelect an option: ").strip()

        if choice == "1":
            clear_screen()
            show_banner()
            print("""
STARTUP INSTRUCTIONS
--------------------
Open three separate terminals in your project directory.

Terminal 1 — TCP server:
    py server/main.py

Terminal 2 — WebSocket gateway:
    py gateway/websocket_server.py

Terminal 3 — Frontend (only when you want the UI):
    cd frontend
    npm run dev

For a terminal-only experience, you can skip Terminal 3.
""")
            input("\nPress Enter to return to the guide...")

        elif choice == "2":
            clear_screen()
            show_banner()
            print("""
CLOUDCHAT COMMAND GUIDE
-----------------------
/join general       Join the general channel
/join developers    Join the developers channel
/join random        Join the random channel
/pm <user> <text>   Send a private message
/users              View connected users
/rooms              View available channels
/quit               Exit the client

Note: Exact command support depends on the server protocol.
""")
            input("\nPress Enter to return to the guide...")

        elif choice == "3":
            print("""
To launch CloudChat services, open another terminal
in your project directory and run:

    py server/main.py

Then open a second terminal and run:

    py gateway/websocket_server.py

This guide does not automatically start the services.
""")
            input("\nPress Enter to return to the guide...")

        elif choice == "4":
            print("\nThank you for exploring CloudChat!")
            print("Goodbye!")
            break

        else:
            input("\nInvalid option. Press Enter to try again.")


if __name__ == "__main__":
    main()
