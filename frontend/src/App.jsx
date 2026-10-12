import { useCallback, useEffect, useRef, useState } from "react";
import {
  Hash,
  MessageCircle,
  Plus,
  Search,
  Send,
  Settings,
  Users,
  Zap,
  Wifi,
  WifiOff,
  ArrowDownLeft,
  MoreHorizontal,
} from "lucide-react";
import "./App.css";

const WS_URL =
  import.meta.env.VITE_WS_URL || "ws://127.0.0.1:8765";

const INITIAL_ROOMS = ["general", "developers", "random"];

const INITIAL_MESSAGES = {
  general: [],
  developers: [],
  random: [],
};

function createId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function normalizeName(name = "") {
  return name.trim().toLowerCase();
}

function getConversationKey(name) {
  return `direct:${normalizeName(name)}`;
}

function formatTime(value) {
  if (!value) {
    return new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }

  if (/^\d{2}:\d{2}:\d{2}$/.test(value)) {
    return value.slice(0, 5);
  }

  const date = new Date(value);

  if (!Number.isNaN(date.getTime())) {
    return date.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }

  return value;
}

function getInitials(name = "?") {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("");
}

function App() {
  const [username, setUsername] = useState(
    () => localStorage.getItem("cloudchat_username") || ""
  );

  const [usernameInput, setUsernameInput] = useState(
    () => localStorage.getItem("cloudchat_username") || ""
  );

  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState("");

  const [activeTab, setActiveTab] = useState("channels");
  const [activeRoom, setActiveRoom] = useState("general");
  const [activeDirectMessage, setActiveDirectMessage] = useState(null);

  const [rooms, setRooms] = useState(INITIAL_ROOMS);
  const [members, setMembers] = useState([]);
  const [directConversations, setDirectConversations] = useState([]);
  const [unreadCounts, setUnreadCounts] = useState({});

  const [messagesByRoom, setMessagesByRoom] = useState(() => ({
    ...INITIAL_MESSAGES,
  }));

  const [messageInput, setMessageInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  const [systemMessages, setSystemMessages] = useState([
    {
      id: createId(),
      type: "system",
      message: "Welcome to #general. Connect to start chatting!",
      timestamp: "",
    },
  ]);

  const socketRef = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const intentionalCloseRef = useRef(false);

  const usernameRef = useRef(username);
  const activeConversationRef = useRef("general");

  const activeConversationKey = activeDirectMessage
    ? getConversationKey(activeDirectMessage)
    : activeRoom;

  const activeMessages =
    messagesByRoom[activeConversationKey] || [];

  const onlineMembers = members.filter(
    (member) =>
      normalizeName(member) !== normalizeName(username)
  );

  const filteredRooms = rooms.filter((room) =>
    room.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredConversations = directConversations.filter((name) =>
    name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  useEffect(() => {
    usernameRef.current = username;
  }, [username]);

  useEffect(() => {
    activeConversationRef.current = activeConversationKey;
  }, [activeConversationKey]);

  const addMessage = useCallback((key, message) => {
    setMessagesByRoom((previous) => ({
      ...previous,
      [key]: [...(previous[key] || []), message],
    }));
  }, []);

  const addSystemMessage = useCallback(
    (message, timestamp = "") => {
      setSystemMessages((previous) => [
        ...previous.slice(-99),
        {
          id: createId(),
          type: "system",
          message,
          timestamp,
        },
      ]);
    },
    []
  );

  const rememberConversation = useCallback((name) => {
    if (!name) return;

    setDirectConversations((previous) => {
      const existing = previous.find(
        (item) =>
          normalizeName(item) === normalizeName(name)
      );

      if (existing) return previous;

      return [name, ...previous];
    });
  }, []);

  const markConversationRead = useCallback((name) => {
    if (!name) return;

    const key = getConversationKey(name);

    setUnreadCounts((previous) => {
      if (!previous[key]) return previous;

      return {
        ...previous,
        [key]: 0,
      };
    });
  }, []);

  const sendSocketMessage = useCallback((payload) => {
    const socket = socketRef.current;

    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return false;
    }

    socket.send(
      typeof payload === "string"
        ? payload
        : JSON.stringify(payload)
    );

    return true;
  }, []);

  const connect = useCallback(
    (requestedUsername) => {
      const cleanUsername = requestedUsername.trim();

      if (!cleanUsername) {
        setConnectionError("Enter a username to connect.");
        return;
      }

      if (cleanUsername.length > 24) {
        setConnectionError(
          "Username must be 24 characters or fewer."
        );
        return;
      }

      if (socketRef.current?.readyState === WebSocket.OPEN) {
        return;
      }

      if (
        socketRef.current?.readyState === WebSocket.CONNECTING
      ) {
        return;
      }

      setConnecting(true);
      setConnectionError("");
      intentionalCloseRef.current = false;

      let socket;

      try {
        socket = new WebSocket(WS_URL);
      } catch {
        setConnecting(false);
        setConnectionError(
          "Could not connect to the CloudChat gateway."
        );
        return;
      }

      socketRef.current = socket;

      socket.onopen = () => {
        if (socketRef.current !== socket) return;

        // The gateway expects the username as the first frame.
        socket.send(cleanUsername);

        usernameRef.current = cleanUsername;

        setUsername(cleanUsername);
        setUsernameInput(cleanUsername);

        localStorage.setItem(
          "cloudchat_username",
          cleanUsername
        );

        setConnected(true);
        setConnecting(false);
        setConnectionError("");

        addSystemMessage("Connected to CloudChat gateway.");

        socket.send(
          JSON.stringify({
            type: "command",
            command: "/users",
          })
        );

        socket.send(
          JSON.stringify({
            type: "command",
            command: "/rooms",
          })
        );

        socket.send(
          JSON.stringify({
            type: "command",
            command: `/join ${activeRoom}`,
          })
        );
      };

      socket.onmessage = (event) => {
        let data;

        try {
          data = JSON.parse(event.data);
        } catch {
          addSystemMessage(
            "Received an unreadable server message."
          );
          return;
        }

        if (data.type === "users") {
          const receivedUsers = Array.isArray(data.users)
            ? data.users
            : [];

          setMembers(
            [
              ...new Set(
                receivedUsers.filter(
                  (name) =>
                    typeof name === "string" && name.trim()
                )
              ),
            ].sort((a, b) => a.localeCompare(b))
          );

          return;
        }

        if (data.type === "rooms") {
          if (Array.isArray(data.rooms)) {
            setRooms((previous) => [
              ...new Set([
                ...INITIAL_ROOMS,
                ...data.rooms.filter(
                  (room) => typeof room === "string"
                ),
              ]),
            ]);
          }

          return;
        }

        if (data.type === "error") {
          const errorMessage =
            data.message || "A connection error occurred.";

          setConnectionError(errorMessage);
          addSystemMessage(errorMessage);

          return;
        }

        if (data.type === "system") {
          const text = data.message || "System notification";

          addSystemMessage(text, data.timestamp);

          const onlineMatch = text.match(
            /^Online users:\s*(.*)$/i
          );

          if (onlineMatch) {
            const names = onlineMatch[1]
              .split(",")
              .map((name) => name.trim())
              .filter(Boolean);

            setMembers(names);
          }

          const joinedMatch = text.match(
            /^(.+?) joined the chat$/i
          );

          if (joinedMatch) {
            setMembers((previous) => {
              const name = joinedMatch[1];

              if (
                previous.some(
                  (member) =>
                    normalizeName(member) ===
                    normalizeName(name)
                )
              ) {
                return previous;
              }

              return [...previous, name].sort((a, b) =>
                a.localeCompare(b)
              );
            });
          }

          const disconnectedMatch = text.match(
            /^(.+?) disconnected$/i
          );

          if (disconnectedMatch) {
            const name = disconnectedMatch[1];

            setMembers((previous) =>
              previous.filter(
                (member) =>
                  normalizeName(member) !==
                  normalizeName(name)
              )
            );
          }

          return;
        }

        if (data.type === "chat") {
          const roomName = data.room || "general";

          addMessage(roomName, {
            id: createId(),
            type: "chat",
            username: data.username || "Unknown",
            message: data.message || "",
            timestamp: data.timestamp || "",
          });

          setRooms((previous) =>
            previous.includes(roomName)
              ? previous
              : [...previous, roomName]
          );

          return;
        }

        if (data.type === "private") {
          const sender = data.username || "Unknown";
          const currentUsername = usernameRef.current;
          const recipient =
            data.recipient || currentUsername;

          const isOwnMessage =
            normalizeName(sender) ===
            normalizeName(currentUsername);

          const otherUser = isOwnMessage
            ? recipient
            : sender;

          const conversationKey =
            getConversationKey(otherUser);

          rememberConversation(otherUser);

          addMessage(conversationKey, {
            id: createId(),
            type: "private",
            username: sender,
            message: data.message || "",
            timestamp: data.timestamp || "",
            outgoing: isOwnMessage,
          });

          // Ignore our own messages when calculating unread counts.
          // Messages received in the open conversation are read.
          if (
            !isOwnMessage &&
            activeConversationRef.current !== conversationKey
          ) {
            setUnreadCounts((previous) => ({
              ...previous,
              [conversationKey]:
                (previous[conversationKey] || 0) + 1,
            }));
          }

          return;
        }
      };

      socket.onerror = () => {
        if (socketRef.current !== socket) return;

        setConnectionError(
          "Unable to reach the gateway. Make sure the Python server and WebSocket gateway are running."
        );

        setConnecting(false);
      };

      socket.onclose = () => {
        if (socketRef.current !== socket) return;

        socketRef.current = null;

        setConnected(false);
        setConnecting(false);
        setMembers([]);

        if (!intentionalCloseRef.current) {
          addSystemMessage(
            "Disconnected from CloudChat gateway."
          );
        }
      };
    },
    [
      activeRoom,
      addMessage,
      addSystemMessage,
      rememberConversation,
    ]
  );

  const disconnect = useCallback(() => {
    intentionalCloseRef.current = true;

    const socket = socketRef.current;
    socketRef.current = null;

    setConnected(false);
    setConnecting(false);
    setMembers([]);

    if (socket) {
      try {
        socket.close();
      } catch {
        // Ignore close errors.
      }
    }

    addSystemMessage("You disconnected from CloudChat.");
  }, [addSystemMessage]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [activeMessages, systemMessages]);

  useEffect(() => {
    return () => {
      intentionalCloseRef.current = true;

      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, []);

  const selectRoom = (room) => {
    setActiveRoom(room);
    setActiveDirectMessage(null);
    setActiveTab("channels");

    activeConversationRef.current = room;

    if (connected) {
      sendSocketMessage({
        type: "command",
        command: `/join ${room}`,
      });
    }
  };

  const selectConversation = (name) => {
    const key = getConversationKey(name);

    setActiveDirectMessage(name);
    setActiveTab("messages");

    activeConversationRef.current = key;

    markConversationRead(name);
    rememberConversation(name);
  };

  const openMemberConversation = (name) => {
    if (normalizeName(name) === normalizeName(username)) {
      return;
    }

    selectConversation(name);

    setTimeout(() => {
      inputRef.current?.focus();
    }, 0);
  };

  const sendMessage = (event) => {
    event.preventDefault();

    const text = messageInput.trim();

    if (!text) return;

    if (
      !connected ||
      socketRef.current?.readyState !== WebSocket.OPEN
    ) {
      setConnectionError(
        "Connect to CloudChat before sending messages."
      );
      return;
    }

    if (text.startsWith("/")) {
      const sent = sendSocketMessage({
        type: "command",
        command: text,
      });

      if (sent) setMessageInput("");

      return;
    }

    if (activeDirectMessage) {
      if (
        normalizeName(activeDirectMessage) ===
        normalizeName(username)
      ) {
        setConnectionError(
          "You cannot send a private message to yourself."
        );
        return;
      }

      const sent = sendSocketMessage({
        type: "command",
        command: `/pm ${activeDirectMessage} ${text}`,
      });

      if (sent) {
        addMessage(
          getConversationKey(activeDirectMessage),
          {
            id: createId(),
            type: "private",
            username,
            message: text,
            timestamp: new Date()
              .toTimeString()
              .slice(0, 8),
            outgoing: true,
            pending: true,
          }
        );

        rememberConversation(activeDirectMessage);
        markConversationRead(activeDirectMessage);

        setMessageInput("");
      }

      return;
    }

    const sent = sendSocketMessage({
      type: "chat",
      message: text,
    });

    if (sent) setMessageInput("");
  };

  const handleComposerKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage(event);
    }
  };

  const activeTitle =
    activeDirectMessage || activeRoom;

  const activeDescription = activeDirectMessage
    ? `Private conversation with ${activeDirectMessage}`
    : activeRoom === "general"
      ? "A place for the team to talk"
      : activeRoom === "developers"
        ? "Build, share, and discuss"
        : activeRoom === "random"
          ? "Anything that doesn't fit elsewhere"
          : `Welcome to the #${activeRoom} channel`;

  const totalUnreadCount = Object.values(
    unreadCounts
  ).reduce((total, count) => total + count, 0);

  const memberCountLabel =
    `${members.length} ${
      members.length === 1 ? "member" : "members"
    } online`;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">
            <Zap size={20} />
          </div>

          <div className="brand-copy">
            <span className="brand-name">CloudChat</span>
            <span className="brand-subtitle">
              TEAM WORKSPACE
            </span>
          </div>
        </div>

        <button
          className="workspace-selector"
          type="button"
        >
          <div className="workspace-avatar">C</div>

          <div className="workspace-info">
            <strong>CloudChat HQ</strong>
            <span>
              {connected ? "Connected" : "Workspace"}
            </span>
          </div>

          <MoreHorizontal size={18} />
        </button>

        <label className="search-box">
          <Search size={16} />

          <input
            type="search"
            placeholder="Search..."
            value={searchQuery}
            onChange={(event) =>
              setSearchQuery(event.target.value)
            }
          />

          <kbd>/</kbd>
        </label>

        <div className="sidebar-tabs">
          <button
            type="button"
            className={
              activeTab === "channels" ? "active" : ""
            }
            onClick={() => {
              setActiveTab("channels");
              setActiveDirectMessage(null);
              activeConversationRef.current = activeRoom;
            }}
          >
            <Hash size={16} />
            Channels
          </button>

          <button
            type="button"
            className={
              activeTab === "messages" ? "active" : ""
            }
            onClick={() => setActiveTab("messages")}
          >
            <MessageCircle size={16} />
            Messages

            {totalUnreadCount > 0 && (
              <span className="tab-count">
                {totalUnreadCount > 99
                  ? "99+"
                  : totalUnreadCount}
              </span>
            )}
          </button>
        </div>

        {activeTab === "channels" ? (
          <div className="channel-section">
            <div className="section-heading">
              <span>CHANNELS</span>

              <button
                type="button"
                className="icon-button"
                title="Create a channel"
                onClick={() => {
                  const roomName = window.prompt(
                    "Enter a channel name (letters, numbers, - or _):"
                  );

                  if (!roomName?.trim()) return;

                  const cleanRoom = roomName
                    .trim()
                    .toLowerCase()
                    .replace(/\s+/g, "-");

                  if (
                    !/^[a-z0-9_-]{1,30}$/.test(cleanRoom)
                  ) {
                    window.alert(
                      "Use 1–30 letters, numbers, hyphens, or underscores."
                    );
                    return;
                  }

                  setRooms((previous) =>
                    previous.includes(cleanRoom)
                      ? previous
                      : [...previous, cleanRoom]
                  );

                  setMessagesByRoom((previous) => ({
                    ...previous,
                    [cleanRoom]:
                      previous[cleanRoom] || [],
                  }));

                  selectRoom(cleanRoom);
                }}
              >
                <Plus size={16} />
              </button>
            </div>

            <div className="channel-list">
              {filteredRooms.map((room) => (
                <button
                  type="button"
                  key={room}
                  className={`channel-item ${
                    activeRoom === room &&
                    !activeDirectMessage
                      ? "active"
                      : ""
                  }`}
                  onClick={() => selectRoom(room)}
                >
                  <Hash size={16} />
                  <span>{room}</span>
                </button>
              ))}

              {filteredRooms.length === 0 && (
                <p className="empty-state">
                  No matching channels.
                </p>
              )}
            </div>
          </div>
        ) : (
          <div className="channel-section">
            <div className="section-heading">
              <span>DIRECT MESSAGES</span>
            </div>

            <div className="channel-list">
              {filteredConversations.map((name) => {
                const unread =
                  unreadCounts[getConversationKey(name)] ||
                  0;

                return (
                  <button
                    type="button"
                    key={normalizeName(name)}
                    className={`channel-item dm-item ${
                      normalizeName(
                        activeDirectMessage || ""
                      ) === normalizeName(name)
                        ? "active"
                        : ""
                    }`}
                    onClick={() =>
                      selectConversation(name)
                    }
                  >
                    <span className="small-avatar">
                      {getInitials(name)}
                    </span>

                    <span>{name}</span>

                    {unread > 0 ? (
                      <span className="tab-count">
                        {unread > 99 ? "99+" : unread}
                      </span>
                    ) : (
                      <span className="online-dot" />
                    )}
                  </button>
                );
              })}

              {filteredConversations.length === 0 && (
                <p className="empty-state">
                  No conversations yet. Select someone from
                  Members to start a private chat.
                </p>
              )}

              <div className="section-heading contacts-heading">
                <span>ONLINE MEMBERS</span>
              </div>

              {onlineMembers.map((name) => (
                <button
                  type="button"
                  className="channel-item dm-item"
                  key={normalizeName(name)}
                  onClick={() =>
                    openMemberConversation(name)
                  }
                >
                  <span className="small-avatar">
                    {getInitials(name)}
                  </span>

                  <span>{name}</span>

                  <span className="online-dot" />
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="sidebar-bottom">
          <div className="profile-avatar">
            {getInitials(username || "G")}
          </div>

          <div className="profile-info">
            <strong>{username || "Guest"}</strong>
            <span>{connected ? "Online" : "Offline"}</span>
          </div>

          <button
            type="button"
            className="icon-button settings-button"
            title="Connection settings"
            onClick={() => {
              if (connected) {
                disconnect();
              } else {
                document
                  .getElementById("username-input")
                  ?.focus();
              }
            }}
          >
            <Settings size={17} />
          </button>
        </div>
      </aside>

      <main className="chat-panel">
        <header className="chat-header">
          <div className="chat-header-title">
            <div className="title-icon">
              {activeDirectMessage ? (
                <MessageCircle size={18} />
              ) : (
                <Hash size={19} />
              )}
            </div>

            <div>
              <h1>
                {activeDirectMessage
                  ? activeTitle
                  : `#${activeTitle}`}
              </h1>

              <p>{activeDescription}</p>
            </div>
          </div>

          <div
            className="header-actions"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "16px",
            }}
          >
            <div
              className={`connection-status ${
                connected
                  ? "connected"
                  : "disconnected"
              }`}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              {connected ? (
                <Wifi size={15} />
              ) : (
                <WifiOff size={15} />
              )}

              <span>
                {connected ? "Live" : "Offline"}
              </span>
            </div>

            <div
              className="header-members"
              title="Total connected workspace members"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "7px",
                whiteSpace: "nowrap",
              }}
            >
              <Users size={16} />
              <span>{memberCountLabel}</span>
            </div>
          </div>
        </header>

        {!connected && (
          <div className="connection-banner">
            <div className="banner-copy">
              <strong>Connect to CloudChat</strong>

              <span>
                Enter a username to join the workspace and
                start chatting.
              </span>
            </div>

            <form
              className="connect-form"
              onSubmit={(event) => {
                event.preventDefault();
                connect(usernameInput);
              }}
            >
              <input
                id="username-input"
                value={usernameInput}
                onChange={(event) =>
                  setUsernameInput(event.target.value)
                }
                placeholder="Your username"
                maxLength={24}
                autoComplete="nickname"
                disabled={connecting}
              />

              <button type="submit" disabled={connecting}>
                {connecting
                  ? "Connecting..."
                  : "Connect"}
              </button>
            </form>
          </div>
        )}

        {connectionError && (
          <div className="error-banner">
            <span>{connectionError}</span>

            <button
              type="button"
              onClick={() => setConnectionError("")}
              aria-label="Dismiss error"
            >
              ×
            </button>
          </div>
        )}

        <section className="messages-area">
          {!activeDirectMessage && (
            <div className="channel-intro">
              <div className="intro-hash">
                <Hash size={27} />
              </div>

              <h2>Welcome to #{activeRoom}!</h2>

              <p>
                This is the beginning of the{" "}
                <strong>#{activeRoom}</strong> channel.
              </p>

              <div className="divider">
                <span />
                <small>MESSAGES</small>
                <span />
              </div>
            </div>
          )}

          {activeDirectMessage &&
            activeMessages.length === 0 && (
              <div className="channel-intro direct-intro">
                <div className="intro-hash">
                  <MessageCircle size={26} />
                </div>

                <h2>
                  Chat with {activeDirectMessage}
                </h2>

                <p>
                  This is the beginning of your private
                  conversation. Say hello!
                </p>
              </div>
            )}

          {systemMessages.map((message) => (
            <div
              className="system-message"
              key={message.id}
            >
              <span>{message.message}</span>

              {message.timestamp && (
                <time>{formatTime(message.timestamp)}</time>
              )}
            </div>
          ))}

          {activeMessages.map((message) => {
            const isOwnMessage =
              normalizeName(message.username) ===
              normalizeName(username);

            return (
              <article
                className={`message-row ${
                  isOwnMessage ? "own-message" : ""
                }`}
                key={message.id}
              >
                <div
                  className={`message-avatar ${
                    message.type === "private"
                      ? "private-avatar"
                      : ""
                  }`}
                >
                  {getInitials(message.username)}
                </div>

                <div
                  className="message-content"
                  style={{
                    minWidth: 0,
                    flex: 1,
                  }}
                >
                  <div
                    className="message-meta"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                      width: "100%",
                      minWidth: 0,
                    }}
                  >
                    <strong
                      style={{
                        flexShrink: 0,
                      }}
                    >
                      {message.username}
                    </strong>

                    <time
                      style={{
                        marginLeft: "auto",
                        flexShrink: 0,
                        whiteSpace: "nowrap",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {formatTime(message.timestamp)}
                    </time>

                    {message.type === "private" && (
                      <span className="private-label">
                        <ArrowDownLeft size={12} />
                        Direct
                      </span>
                    )}
                  </div>

                  <p>{message.message}</p>

                  {message.pending && (
                    <span className="message-delivery-status">
                      Sent
                    </span>
                  )}
                </div>
              </article>
            );
          })}

          <div ref={messagesEndRef} />
        </section>

        <div className="composer-area">
          <form
            className="composer"
            onSubmit={sendMessage}
          >
            <button
              type="button"
              className="composer-plus"
              title="Message tips"
              onClick={() =>
                addSystemMessage(
                  activeDirectMessage
                    ? `Private message to ${activeDirectMessage}.`
                    : `Sending to #${activeRoom}. Use /users to list online users or /rooms to list channels.`
                )
              }
            >
              <Plus size={19} />
            </button>

            <input
              ref={inputRef}
              value={messageInput}
              onChange={(event) =>
                setMessageInput(event.target.value)
              }
              onKeyDown={handleComposerKeyDown}
              placeholder={
                connected
                  ? activeDirectMessage
                    ? `Message ${activeDirectMessage}...`
                    : `Message #${activeRoom}...`
                  : "Connect to start chatting..."
              }
              disabled={!connected}
              maxLength={2000}
              aria-label="Write a message"
            />

            <button
              type="submit"
              className="send-button"
              disabled={
                !connected || !messageInput.trim()
              }
              title="Send message"
              aria-label="Send message"
            >
              <Send size={17} />
            </button>
          </form>

          <div className="composer-hint">
            <span>
              <kbd>Enter</kbd> to send
            </span>

            <span>{messageInput.length}/2000</span>
          </div>
        </div>
      </main>

      <aside className="members-panel">
        <div className="members-header">
          <div>
            <h2>Members</h2>
            <p>People in your workspace</p>
          </div>

          <span className="members-count">
            {members.length}
          </span>
        </div>

        <div className="member-group">
          <div className="member-group-heading">
            <span className="online-indicator" />
            <span>ONLINE</span>

            <span className="group-count">
              {members.length}
            </span>
          </div>

          {members.length > 0 ? (
            <div className="member-list">
              {members.map((name) => {
                const isSelf =
                  normalizeName(name) ===
                  normalizeName(username);

                return (
                  <button
                    type="button"
                    className={`member-row ${
                      isSelf ? "current-user" : ""
                    }`}
                    key={normalizeName(name)}
                    onClick={() =>
                      openMemberConversation(name)
                    }
                    title={
                      isSelf
                        ? "You"
                        : `Start a private conversation with ${name}`
                    }
                  >
                    <div className="member-avatar">
                      {getInitials(name)}

                      <span className="member-online-dot" />
                    </div>

                    <div className="member-info">
                      <strong>{name}</strong>

                      <span>
                        {isSelf
                          ? "You · Online"
                          : "Online"}
                      </span>
                    </div>

                    {!isSelf && (
                      <MessageCircle
                        className="member-message-icon"
                        size={15}
                      />
                    )}
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="empty-members">
              <div className="empty-members-icon">
                <Users size={22} />
              </div>

              <strong>No members yet</strong>

              <p>
                Online users will appear here when the
                server sends the user list.
              </p>

              {!connected && (
                <span className="members-offline-note">
                  Connect to view members.
                </span>
              )}
            </div>
          )}
        </div>

        <div className="server-card">
          <div className="server-card-heading">
            <div className="server-icon">
              <Zap size={16} />
            </div>

            <div>
              <strong>CloudChat Server</strong>

              <span>
                Python TCP sockets · Multi-threaded
                messaging
              </span>
            </div>
          </div>

          <div className="server-card-status">
            <span
              className={
                connected
                  ? "status-dot online"
                  : "status-dot"
              }
            />

            <span>
              {connected
                ? "Connected to gateway"
                : "Not connected"}
            </span>
          </div>
        </div>
      </aside>
    </div>
  );
}

export default App;