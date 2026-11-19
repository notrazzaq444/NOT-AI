const $ = (selector, scope = document) => scope.querySelector(selector);
const $$ = (selector, scope = document) => [
  ...scope.querySelectorAll(selector),
];
const icon = (name) =>
  `<svg aria-hidden="true"><use href="#i-${name}"></use></svg>`;

const API_ORIGIN = window.location.origin;
const WS_PROTOCOL = window.location.protocol === "https:" ? "wss:" : "ws:";

const state = {
  view: "voice",
  listening: false,
  muted: false,
  signedIn:
    !!localStorage.getItem("firebase_id_token") &&
    localStorage.getItem("firebase_id_token") !== "dummy-dev-token",
  attachment: null,
  callTimer: null,
  callSeconds: 0,
  toastTimer: null,
};

const views = $$("[data-view-panel]");
const messages = $("#messages");
const input = $("#chat-input");

async function initFirebaseSDK() {
  try {
    const res = await fetch(`${API_ORIGIN}/api/firebase-config`);
    if (res.ok) {
      const cfg = await res.json();
      if (
        cfg.apiKey &&
        typeof firebase !== "undefined" &&
        !firebase.apps.length
      ) {
        firebase.initializeApp(cfg);
        setupFirebaseAuthListeners();
      }
    }
  } catch (e) {
    console.error("Failed to fetch Firebase config:", e);
  }
}

function setupFirebaseAuthListeners() {
  if (typeof firebase === "undefined" || !firebase.auth) return;
  firebase.auth().onAuthStateChanged((user) => {
    if (user) {
      handleFirebaseUserSession(user);
    }
  });
}

initFirebaseSDK();

function setView(view) {
  state.view = view;
  views.forEach((panel) =>
    panel.classList.toggle("is-active", panel.dataset.viewPanel === view),
  );
  $$("[data-view]").forEach((button) =>
    button.classList.toggle("is-active", button.dataset.view === view),
  );
  $$(".mobile-nav button").forEach((button) =>
    button.classList.toggle("is-active", button.dataset.view === view),
  );
  $("#sidebar")?.classList.remove("is-open");
  if (view === "chat") {
    requestAnimationFrame(() => {
      if (messages) messages.scrollTop = messages.scrollHeight;
    });
  }
}

function showToast(text) {
  const toast = $("#toast");
  if (!toast) return;
  toast.textContent = text;
  toast.classList.add("is-visible");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(
    () => toast.classList.remove("is-visible"),
    2500,
  );
}

function openModal(id) {
  const modal = $(id);
  if (!modal) return;
  modal.classList.add("is-open");
  modal.setAttribute("aria-hidden", "false");
  setTimeout(() => $("input", modal)?.focus(), 250);
}

function closeModals() {
  $$(".modal").forEach((modal) => {
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
  });
}

function updateAuthUI(userName = "User", userEmail = "user@example.com") {
  $$(".auth-label").forEach(
    (label) =>
      (label.textContent = state.signedIn
        ? userName.split(" ")[0] || "Account"
        : "Sign in"),
  );
  const footer = $(".signin-side small");
  if (footer) {
    footer.textContent = state.signedIn
      ? userEmail || "Personalization & settings"
      : "Sync your intelligence";
  }
  const avatar = $(".account-avatar");
  if (avatar) {
    avatar.innerHTML = state.signedIn
      ? userName.charAt(0).toUpperCase() || "A"
      : icon("user");
  }
  const profileAvatar = $(".profile-avatar");
  if (profileAvatar && state.signedIn) {
    profileAvatar.textContent = userName.charAt(0).toUpperCase() || "U";
  }

  const nameEl = $(".profile-row b");
  const emailEl = $("#profile-email");
  if (nameEl && userName) nameEl.textContent = userName;
  if (emailEl && userEmail) emailEl.textContent = userEmail;
}

function handleAccountClick() {
  openModal(state.signedIn ? "#account-modal" : "#auth-modal");
}

async function handleFirebaseUserSession(user) {
  if (user) {
    try {
      const token = await user.getIdToken();
      localStorage.setItem("firebase_id_token", token);
      localStorage.setItem("not-token", token);
      state.signedIn = true;

      const realEmail = user.email || "user@example.com";
      const realName =
        user.displayName || realEmail.split("@")[0] || "User";

      await fetch(`${API_ORIGIN}/api/auth/sync`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ email: realEmail, name: realName }),
      });

      updateAuthUI(realName, realEmail);
      closeModals();
      showToast(`Signed in as ${realName}`);
      await loadUserSettings();
      await loadUserSessions();
      if (window.notSocket) window.notSocket.connect();
    } catch (err) {
      console.error("Session sync error:", err);
    }
  } else {
    state.signedIn = false;
    localStorage.removeItem("firebase_id_token");
    localStorage.removeItem("not-token");
    updateAuthUI();
  }
}

async function loadUserSettings() {
  const token = localStorage.getItem("firebase_id_token");
  if (!token || token === "dummy-dev-token") return;

  try {
    const response = await fetch(`${API_ORIGIN}/api/user/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.ok) {
      const data = await response.json();
      const userName = data.name || "User";
      const userEmail = data.email || "user@example.com";

      updateAuthUI(userName, userEmail);

      const settingRows = document.querySelectorAll(
        ".account-card .setting-row small",
      );
      if (settingRows.length >= 3) {
        if (data.personality) settingRows[0].textContent = data.personality;
        if (data.voice) settingRows[1].textContent = `${data.voice} · Natural`;
        if (data.language && data.country) {
          settingRows[2].textContent = `Lang: ${data.language}, Country: ${data.country}`;
        }
      }
    }
  } catch (e) {
    console.error("Failed to load user settings:", e);
  }
}

async function loadUserSessions() {
  const token = localStorage.getItem("firebase_id_token");
  if (!token || token === "dummy-dev-token") return;

  try {
    const response = await fetch(`${API_ORIGIN}/api/sessions`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.ok) {
      const sessions = await response.json();
      const historyContainer = $(".history");
      if (!historyContainer) return;

      historyContainer.innerHTML = "<p>RECENT</p>";

      if (sessions.length === 0) {
        historyContainer.innerHTML += `<button style="color: #555; cursor: default; background: none; border: none; padding: 9px 4px; font-size: 12px;">No recent chats</button>`;
        return;
      }

      sessions.forEach((sess) => {
        const btnWrapper = document.createElement("div");
        btnWrapper.style.cssText =
          "display: flex; align-items: center; justify-content: space-between; margin-bottom: 3px;";

        const chatBtn = document.createElement("button");
        chatBtn.textContent = sess.title || "Untitled Chat";
        chatBtn.style.cssText =
          "flex: 1; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; background: none; text-align: left; color: #747c7a; font-size: 12px; border-radius: 7px; padding: 9px 4px; border: none; cursor: pointer;";
        chatBtn.addEventListener("click", () => loadSessionMessages(sess.id));

        const deleteBtn = document.createElement("button");
        deleteBtn.innerHTML = "×";
        deleteBtn.title = "Delete chat";
        deleteBtn.style.cssText =
          "background: none; border: none; color: #ff5555; font-size: 16px; padding: 0 8px; cursor: pointer; opacity: 0.6;";
        deleteBtn.onmouseover = () => (deleteBtn.style.opacity = "1");
        deleteBtn.onmouseout = () => (deleteBtn.style.opacity = "0.6");

        deleteBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          if (confirm("Delete this conversation?")) {
            await deleteSession(sess.id);
          }
        });

        btnWrapper.appendChild(chatBtn);
        btnWrapper.appendChild(deleteBtn);
        historyContainer.appendChild(btnWrapper);
      });
    }
  } catch (e) {
    console.error("Failed to load sessions:", e);
  }
}

async function loadSessionMessages(sessionId) {
  const token = localStorage.getItem("firebase_id_token");
  try {
    const response = await fetch(`${API_ORIGIN}/api/chat/history/${sessionId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.ok) {
      const messagesList = await response.json();
      activeSessionId = sessionId;
      if (messages) {
        messages.innerHTML = "";
        if (messagesList.length === 0) {
          messages.innerHTML = `<div class="welcome-message"><span class="mini-logo">N</span><h1>What can I help with?</h1><p>Start a new conversation by typing below or switching to voice.</p></div>`;
        } else {
          messagesList.forEach((msg) => {
            createMessage(msg.role, msg.content);
          });
        }
      }
      setView("chat");
      showToast("Conversation loaded.");
    }
  } catch (e) {
    console.error("Failed to load chat history:", e);
  }
}

async function deleteSession(sessionId) {
  const token = localStorage.getItem("firebase_id_token");
  try {
    const response = await fetch(`${API_ORIGIN}/api/chat/session/${sessionId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.ok) {
      showToast("Chat deleted successfully");
      await loadUserSessions();
      if (activeSessionId === sessionId) {
        activeSessionId = "session-" + Math.random().toString(36).substring(2, 9);
        if (messages) {
          messages.innerHTML = `<div class="welcome-message"><span class="mini-logo">N</span><h1>What can I help with?</h1><p>Start a new conversation by typing below or switching to voice.</p></div>`;
        }
      }
    } else {
      showToast("Failed to delete chat");
    }
  } catch (e) {
    console.error("Delete session error:", e);
    showToast("Failed to delete chat");
  }
}

function initAccountSettings() {
  const settingRows = document.querySelectorAll(".account-card .setting-row");
  settingRows.forEach((row, index) => {
    row.addEventListener("click", async () => {
      const token = localStorage.getItem("firebase_id_token");
      if (!token || token === "dummy-dev-token") {
        showToast("Please sign in first to save settings.");
        return;
      }

      if (index === 0) {
        const currentVal = prompt(
          "Enter AI Personality (e.g., Calm, direct and thoughtful):",
          "Calm, direct and thoughtful",
        );
        if (currentVal) {
          const res = await apiPost("/api/user/personality", {
            personality: currentVal,
          });
          if (res) {
            showToast("AI Personality updated!");
            loadUserSettings();
          }
        }
      } else if (index === 1) {
        const newVoice = prompt(
          "Select Voice (e.g., Nova, Echo, Alloy, Shimmer):",
          "Nova",
        );
        if (newVoice) {
          const res = await apiPost("/api/user/voice", { voice: newVoice });
          if (res) {
            showToast("Voice preference updated!");
            loadUserSettings();
          }
        }
      } else if (index === 2) {
        const lang = prompt(
          "Enter preferred language code (e.g., en, ur, ar):",
          "en",
        );
        const country = prompt(
          "Enter country code (e.g., PK, US):",
          "PK",
        );
        if (lang && country) {
          try {
            const response = await fetch(`${API_ORIGIN}/api/user/settings`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
              },
              body: JSON.stringify({ language: lang, country: country }),
            });
            if (response.ok) {
              showToast("Preferences saved successfully!");
              loadUserSettings();
            } else {
              const err = await response.json();
              alert(err.detail || "Error updating preferences.");
            }
          } catch (e) {
            alert("Network error while saving preferences.");
          }
        }
      }
    });
  });

  const editProfileBtn = document.querySelector(".profile-row button");
  if (editProfileBtn) {
    editProfileBtn.addEventListener("click", async () => {
      const currentName =
        document.querySelector(".profile-row b")?.textContent || "User";
      const newName = prompt("Enter your display name:", currentName);
      if (newName && newName.trim()) {
        const nameEl = document.querySelector(".profile-row b");
        const emailEl = $("#profile-email");
        if (nameEl) nameEl.textContent = newName.trim();
        updateAuthUI(
          newName.trim(),
          emailEl?.textContent || "",
        );
        if (
          typeof firebase !== "undefined" &&
          firebase.auth &&
          firebase.auth().currentUser
        ) {
          await firebase
            .auth()
            .currentUser.updateProfile({ displayName: newName.trim() });
          await handleFirebaseUserSession(firebase.auth().currentUser);
        }
        showToast("Display name updated!");
      }
    });
  }
}

async function apiPost(endpoint, data) {
  const token = localStorage.getItem("firebase_id_token") || "dummy-dev-token";
  try {
    const response = await fetch(`${API_ORIGIN}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    });
    if (response.ok) return await response.json();
    const err = await response.json();
    alert(err.detail || "Operation failed.");
    return null;
  } catch (e) {
    console.error("API Error:", e);
    alert("Network request failed.");
    return null;
  }
}

function toggleVoice() {
  if (state.listening) {
    if (window.NOTAudio) window.NOTAudio.stopListening();
  } else {
    if (window.NOTAudio) {
      window.NOTAudio.startListening((text) => {
        if (text) {
          $(".welcome-message")?.remove();
          createMessage("user", text);
          sendMessageToBackend(text);
        }
      });
    }
  }
}

window.addEventListener("not:listening", (e) => {
  state.listening = e.detail;
  const orb = $("#voice-orb");
  const bars = $("#voice-bars");
  const title = $("#voice-title");
  const subtitle = $("#voice-subtitle");
  const kicker = $("#voice-kicker");
  const callStatus = $("#call-status");

  if (orb) orb.classList.toggle("is-listening", state.listening);
  if (bars) bars.classList.toggle("is-active", state.listening);
  if (title)
    title.textContent = state.listening ? "I'm listening…" : "How can I help?";
  if (subtitle)
    subtitle.textContent = state.listening
      ? "Speak naturally — pause when you're done"
      : "Tap the orb and start speaking";
  if (kicker)
    kicker.textContent = state.listening ? "VOICE ACTIVE" : "GOOD EVENING";
  if (callStatus && state.listening) callStatus.textContent = "Listening…";
});

window.addEventListener("not:speaking", (e) => {
  const speaking = e.detail;
  const title = $("#voice-title");
  const callStatus = $("#call-status");
  if (title && speaking) title.textContent = "NOT is speaking…";
  if (callStatus && speaking) callStatus.textContent = "NOT is speaking…";
});

function escapeHTML(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

function createMessage(role, content, isHTML = false) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const rendered = isHTML ? content : escapeHTML(content);
  if (role === "assistant") {
    article.innerHTML = `<span class="message-avatar">N</span><div class="message-body"><span class="message-name">NOT</span><div class="message-text">${rendered}</div><div class="response-actions"><button class="copy-response">${icon("copy")}<span>Copy</span></button></div></div>`;
  } else {
    article.innerHTML = `<div class="message-body"><div class="message-text"><p>${rendered}</p></div></div>`;
  }
  if (messages) {
    messages.append(article);
    messages.scrollTop = messages.scrollHeight;
  }
  return article;
}

async function speakText(text) {
  if (state.muted || !text || !text.trim()) return;
  try {
    const response = await fetch(
      `${API_ORIGIN}/api/tts?text=${encodeURIComponent(text)}`,
    );
    if (response.ok) {
      const audioBlob = await response.blob();
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      audio.play();
    }
  } catch (e) {
    console.error("TTS Audio playback failed:", e);
  }
}

let activeSessionId = "session-" + Math.random().toString(36).substring(2, 9);

async function sendMessageToBackend(text) {
  const clean = text.trim();
  if (!clean) return;

  $(".welcome-message")?.remove();
  createMessage("user", clean);

  const assistantArticle = createMessage("assistant", "");
  const textDiv = assistantArticle.querySelector(".message-text");
  let accumulatedResponse = "";

  const token = localStorage.getItem("firebase_id_token") || "dummy-dev-token";
  
  // Register session on backend first so it never throws 404 or foreign key errors
  try {
    const sessRes = await fetch(`${API_ORIGIN}/api/session`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`
      }
    });
    if (sessRes.ok) {
      const sessData = await sessRes.json();
      if (sessData.session_id) {
        activeSessionId = sessData.session_id;
      }
    }
  } catch (e) {
    console.error("Session creation prefix error:", e);
  }

  const wsUrl = `${WS_PROTOCOL}//${window.location.host}/ws/${activeSessionId}?token=${encodeURIComponent(token)}`;
  const socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    socket.send(
      JSON.stringify({
        text: clean,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      }),
    );
  };

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "token") {
      textDiv.textContent += data.text;
      accumulatedResponse += data.text;
      if (messages) messages.scrollTop = messages.scrollHeight;
    } else if (data.type === "end") {
      socket.close();
      speakText(accumulatedResponse);
      loadUserSessions();
    } else if (data.type === "error") {
      textDiv.textContent += ` [Error: ${data.message}]`;
    }
  };

  socket.onerror = () => {
    textDiv.textContent = "Connection error with AI service.";
  };
}

function sendMessage(text) {
  sendMessageToBackend(text);
}

function clearAttachment() {
  state.attachment = null;
  const fileInput = $("#file-input");
  if (fileInput) fileInput.value = "";
  const preview = $("#attachment-preview");
  if (preview) {
    preview.hidden = true;
    preview.replaceChildren();
  }
}

function startCall() {
  const overlay = $("#call-overlay");
  if (!overlay) return;
  overlay.classList.add("is-open");
  overlay.setAttribute("aria-hidden", "false");
  state.callSeconds = 0;
  const callTime = $("#call-time");
  if (callTime) callTime.textContent = "00:00";
  clearInterval(state.callTimer);
  state.callTimer = setInterval(() => {
    state.callSeconds += 1;
    const min = String(Math.floor(state.callSeconds / 60)).padStart(2, "0");
    const sec = String(state.callSeconds % 60).padStart(2, "0");
    if (callTime) callTime.textContent = `${min}:${sec}`;
  }, 1000);

  if (window.NOTAudio) {
    window.NOTAudio.startListening((text) => {
      if (text) {
        const callStatus = $("#call-status");
        if (callStatus) callStatus.textContent = `You: "${text}"`;
        sendMessageToBackend(text);
      }
    });
  }
}

function endCall() {
  const overlay = $("#call-overlay");
  if (overlay) {
    overlay.classList.remove("is-open");
    overlay.setAttribute("aria-hidden", "true");
  }
  clearInterval(state.callTimer);
  state.callTimer = null;
  if (window.NOTAudio) {
    window.NOTAudio.stopListening();
    window.NOTAudio.interrupt();
  }
}

$$("[data-view]").forEach((button) =>
  button.addEventListener("click", () => setView(button.dataset.view)),
);
$$("[data-open-auth]").forEach((button) =>
  button.addEventListener("click", handleAccountClick),
);
$$("[data-close-modal]").forEach((button) =>
  button.addEventListener("click", closeModals),
);
$$("[data-prompt]").forEach((button) =>
  button.addEventListener("click", () => {
    setView("chat");
    sendMessage(button.dataset.prompt);
  }),
);

$("#open-sidebar")?.addEventListener("click", () =>
  $("#sidebar")?.classList.add("is-open"),
);
$("#close-sidebar")?.addEventListener("click", () =>
  $("#sidebar")?.classList.remove("is-open"),
);
$("#new-chat")?.addEventListener("click", () => {
  activeSessionId = "session-" + Math.random().toString(36).substring(2, 9);
  if (messages) {
    messages.innerHTML = `<div class="welcome-message"><span class="mini-logo">N</span><h1>What can I help with?</h1><p>Start a new conversation by typing below or switching to voice.</p></div>`;
  }
  setView("chat");
  showToast("New conversation started.");
});

$("#voice-orb")?.addEventListener("click", toggleVoice);
$("#voice-toggle")?.addEventListener("click", toggleVoice);
$("#voice-mute")?.addEventListener("click", () => {
  state.muted = !state.muted;
  const muteText = $("#voice-mute span");
  if (muteText) muteText.textContent = state.muted ? "Unmute" : "Mute";
  if (state.muted && window.NOTAudio) window.NOTAudio.stopListening();
  showToast(state.muted ? "Microphone muted" : "Microphone active");
});

const chatForm = $("#chat-form");
if (chatForm) {
  chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (input) {
      sendMessage(input.value);
      input.value = "";
      input.style.height = "";
    }
  });
}

if (input) {
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      chatForm?.requestSubmit();
    }
  });
}

$("#attach-file")?.addEventListener("click", () => $("#file-input")?.click());
$("#file-input")?.addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) return;
  state.attachment = file;
  const preview = $("#attachment-preview");
  if (preview) {
    preview.hidden = false;
    preview.innerHTML = `<span class="file-chip">${icon("paperclip")} ${escapeHTML(file.name)} <button aria-label="Remove attachment">×</button></span>`;
    $("button", preview)?.addEventListener("click", clearAttachment);
  }
});

messages?.addEventListener("click", async (event) => {
  const button = event.target.closest(".copy-response, .copy-artifact");
  if (!button) return;
  const source = button.classList.contains("copy-artifact")
    ? button.closest(".artifact")
    : button.closest(".message-body");
  const text = source.innerText.replace(/Copy( code| document)?/g, "").trim();
  try {
    await navigator.clipboard.writeText(text);
    const label = $("span", button);
    if (label) label.textContent = "Copied";
    showToast("Copied to clipboard");
  } catch {
    showToast("Copy is unavailable in this preview");
  }
});

$("#login-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = $("#login-email")?.value;
  const password = $("#login-password")?.value;

  if (typeof firebase !== "undefined" && firebase.apps.length > 0 && firebase.auth) {
    try {
      const userCred = await firebase
        .auth()
        .signInWithEmailAndPassword(email, password);
      await handleFirebaseUserSession(userCred.user);
    } catch (err) {
      alert("Authentication failed: " + err.message);
    }
  } else {
    alert("Firebase Auth SDK not initialized.");
  }
});

$("#google-signin")?.addEventListener("click", async () => {
  if (typeof firebase !== "undefined" && firebase.apps.length > 0 && firebase.auth) {
    try {
      const provider = new firebase.auth.GoogleAuthProvider();
      provider.setCustomParameters({ prompt: "select_account" });
      const result = await firebase.auth().signInWithPopup(provider);
      if (result && result.user) {
        await handleFirebaseUserSession(result.user);
      }
    } catch (err) {
      alert("Google Sign-In failed: " + err.message);
    }
  } else {
    alert("Firebase Auth SDK not loaded.");
  }
});

$("#create-account")?.addEventListener("click", async () => {
  const email = $("#login-email")?.value;
  const password = $("#login-password")?.value;
  if (!email || !password) {
    alert("Please enter both email and password to create an account.");
    return;
  }
  if (typeof firebase !== "undefined" && firebase.apps.length > 0 && firebase.auth) {
    try {
      const userCred = await firebase
        .auth()
        .createUserWithEmailAndPassword(email, password);
      await handleFirebaseUserSession(userCred.user);
      showToast("Account created successfully!");
    } catch (err) {
      alert("Account creation failed: " + err.message);
    }
  } else {
    alert("Firebase Auth SDK not initialized.");
  }
});

$(".text-button")?.addEventListener("click", (event) => {
  const field = $("#login-password");
  if (!field) return;
  field.type = field.type === "password" ? "text" : "password";
  event.currentTarget.textContent = field.type === "password" ? "Show" : "Hide";
});

$("#logout")?.addEventListener("click", async () => {
  if (typeof firebase !== "undefined" && firebase.apps.length > 0 && firebase.auth) {
    try {
      await firebase.auth().signOut();
    } catch (e) {}
  }
  state.signedIn = false;
  localStorage.removeItem("firebase_id_token");
  localStorage.removeItem("not-token");
  updateAuthUI();
  closeModals();
  showToast("Signed out successfully");
  window.location.reload();
});

["#start-call", "#start-call-side", "#mobile-call"].forEach((id) =>
  $(id)?.addEventListener("click", startCall),
);
$("#close-call")?.addEventListener("click", endCall);
$("#end-call")?.addEventListener("click", endCall);
$("#call-mute")?.addEventListener("click", (event) => {
  event.currentTarget.classList.toggle("is-muted");
  const muted = event.currentTarget.classList.contains("is-muted");
  event.currentTarget.lastChild.textContent = muted ? "Unmute" : "Mute";
  const callStatus = $("#call-status");
  if (callStatus)
    callStatus.textContent = muted ? "Microphone muted" : "Listening…";
  if (muted && window.NOTAudio) window.NOTAudio.stopListening();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeModals();
    endCall();
    $("#sidebar")?.classList.remove("is-open");
  }
});

updateAuthUI();
setView("voice");
loadUserSettings();
initAccountSettings();
loadUserSessions();