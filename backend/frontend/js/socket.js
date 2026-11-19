const WS_PROTO = location.protocol === "https:" ? "wss" : "ws";
const WS_BASE = `${WS_PROTO}://${location.host}`;
const API_BASE = `${location.protocol}//${location.host}`;

let state = {
  sessionId: null,
  ws: null,
  status: "disconnected",
  reconnectAttempts: 0,
  reconnectTimer: null,
  manuallyClosed: false,
  pendingMessages: [],
};

function emit(type, detail) {
  window.dispatchEvent(new CustomEvent(`not:${type}`, { detail }));
}

async function createSession() {
  const token = localStorage.getItem("not-token") || "dummy-dev-token";
  const r = await fetch(`${API_BASE}/api/session`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) throw new Error("Session creation failed");
  const data = await r.json();
  state.sessionId = data.session_id;
  return state.sessionId;
}

function connect() {
  if (
    state.ws &&
    (state.ws.readyState === WebSocket.OPEN ||
      state.ws.readyState === WebSocket.CONNECTING)
  )
    return;

  const token = localStorage.getItem("not-token") || "dummy-dev-token";
  state.manuallyClosed = false;

  if (!state.sessionId) {
    createSession()
      .then(() => connect())
      .catch((e) => {
        console.error("[WS] Session Error:", e);
        scheduleReconnect();
      });
    return;
  }

  const url = `${WS_BASE}/ws/${state.sessionId}?token=${encodeURIComponent(token)}`;
  const ws = new WebSocket(url);
  state.ws = ws;

  ws.onopen = () => {
    state.reconnectAttempts = 0;
    state.status = "connected";
    emit("status", "connected");
    while (state.pendingMessages.length > 0) {
      const msg = state.pendingMessages.shift();
      ws.send(msg);
    }
  };

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "start") emit("start");
    else if (msg.type === "token") emit("token", msg.text);
    else if (msg.type === "end") emit("end", msg.content);
    else if (msg.type === "error") emit("error", msg.message);
    else if (msg.type === "camera_request") emit("camera_request", msg);
  };

  ws.onclose = () => {
    state.ws = null;
    state.status = "disconnected";
    if (!state.manuallyClosed) scheduleReconnect();
  };

  ws.onerror = (err) => console.error("[WS] Error:", err);
}

function scheduleReconnect() {
  if (state.reconnectTimer) return;
  state.reconnectAttempts++;
  const delay = Math.min(1000 * 2 ** state.reconnectAttempts, 10000);
  state.status = "reconnecting";
  emit("status", "reconnecting");
  state.reconnectTimer = setTimeout(() => {
    state.reconnectTimer = null;
    connect();
  }, delay);
}

function send(text, language = "en") {
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const payload = JSON.stringify({ text, timezone: tz, language });

  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    state.pendingMessages.push(payload);
    connect();
    return true;
  }
  state.ws.send(payload);
  return true;
}

window.notSocket = {
  connect,
  send,
  disconnect() {
    state.manuallyClosed = true;
    if (state.reconnectTimer) {
      clearTimeout(state.reconnectTimer);
      state.reconnectTimer = null;
    }
    if (state.ws) {
      state.ws.close();
      state.ws = null;
    }
    state.sessionId = null;
    state.status = "disconnected";
    emit("status", "disconnected");
  },
  get status() {
    return state.status;
  },
};
