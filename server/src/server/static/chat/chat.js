(() => {
  "use strict";

  const CHAT_ENDPOINT = "/chat";
  const CONVERSATION_KEY = "iroko.conversation_id";
  const CONVERSATION_PATTERN = /^web-[0-9a-f-]{36}$/;

  class HttpRequestError extends Error {
    constructor(status) {
      super("Chat request failed");
      this.status = status;
    }
  }

  class ResponseValidationError extends Error {}

  const elements = {
    conversationId: document.querySelector("#conversation-id"),
    error: document.querySelector("#request-error"),
    form: document.querySelector("#chat-form"),
    message: document.querySelector("#message"),
    newConversation: document.querySelector("#new-conversation"),
    send: document.querySelector("#send-message"),
    status: document.querySelector("#request-status"),
    transcript: document.querySelector("#transcript"),
  };

  function createConversationId() {
    return `web-${crypto.randomUUID()}`;
  }

  function loadConversationId() {
    const storedId = sessionStorage.getItem(CONVERSATION_KEY);
    if (storedId && CONVERSATION_PATTERN.test(storedId)) {
      return storedId;
    }
    const newId = createConversationId();
    sessionStorage.setItem(CONVERSATION_KEY, newId);
    return newId;
  }

  let conversationId = loadConversationId();

  function renderConversationId() {
    elements.conversationId.textContent = conversationId;
  }

  function clearError() {
    elements.error.hidden = true;
    elements.error.textContent = "";
  }

  function setBusy(isBusy) {
    elements.message.disabled = isBusy;
    elements.send.disabled = isBusy;
    elements.newConversation.disabled = isBusy;
    elements.status.textContent = isBusy ? "Consultando a Iroko…" : "";
  }

  function addMessage(role, text, metadata = "") {
    const article = document.createElement("article");
    const label = document.createElement("strong");
    const body = document.createElement("p");
    article.className = `message message--${role}`;
    label.textContent = role === "user" ? "Tú" : "Iroko";
    body.textContent = text;
    article.append(label, body);
    if (metadata) {
      const details = document.createElement("small");
      details.textContent = metadata;
      article.append(details);
    }
    elements.transcript.append(article);
    article.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  function validateResponse(payload) {
    const valid =
      payload &&
      typeof payload.response === "string" &&
      typeof payload.emotion === "string" &&
      Number.isInteger(payload.duration_ms) &&
      payload.duration_ms >= 0 &&
      payload.conversation_id === conversationId;
    if (!valid) {
      throw new ResponseValidationError("Invalid chat response");
    }
    return payload;
  }

  async function requestTurn(message) {
    const response = await fetch(CHAT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
      }),
    });
    if (!response.ok) {
      throw new HttpRequestError(response.status);
    }
    try {
      return validateResponse(await response.json());
    } catch (error) {
      if (error instanceof ResponseValidationError) {
        throw error;
      }
      throw new ResponseValidationError("Invalid JSON response");
    }
  }

  function errorMessage(error) {
    if (error instanceof HttpRequestError) {
      return `El servidor rechazó la solicitud (HTTP ${error.status}).`;
    }
    if (error instanceof ResponseValidationError) {
      return "El servidor devolvió una respuesta no válida.";
    }
    return "Sin conexión con el servidor local. Intenta nuevamente.";
  }

  async function submitMessage(event) {
    event.preventDefault();
    const message = elements.message.value.trim();
    if (!message) {
      elements.status.textContent = "Escribe un mensaje antes de enviar.";
      return;
    }
    clearError();
    addMessage("user", message);
    elements.message.value = "";
    setBusy(true);
    try {
      const result = await requestTurn(message);
      const metadata = `${result.emotion} · ${result.duration_ms} ms · ${result.conversation_id}`;
      addMessage("assistant", result.response, metadata);
    } catch (error) {
      elements.error.textContent = errorMessage(error);
      elements.error.hidden = false;
    } finally {
      setBusy(false);
      elements.message.focus();
    }
  }

  function startNewConversation() {
    conversationId = createConversationId();
    sessionStorage.setItem(CONVERSATION_KEY, conversationId);
    elements.transcript.replaceChildren();
    clearError();
    elements.status.textContent = "Nueva conversación iniciada.";
    renderConversationId();
    elements.message.focus();
  }

  elements.form.addEventListener("submit", submitMessage);
  elements.newConversation.addEventListener("click", startNewConversation);
  renderConversationId();
})();
