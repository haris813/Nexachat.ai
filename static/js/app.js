"use strict";

const state = {
  config: null,
  conversations: [],
  active: null,
  streaming: false,
  abortController: null,
  search: "",
  showArchived: false,
  attachments: [],
  artifacts: [],
  currentPlan: null,
  whatsapp: null,
  preferences: null,
  user: null,
  recorder: null,
  recordingChunks: [],
  recordingStartedAt: 0,
  recordingTimer: null,
  cancelRecording: false,
  voiceUpload: null,
};

const byId = (id) => document.getElementById(id);
const els = {
  conversationList: byId("conversationList"),
  conversationTitle: byId("conversationTitle"),
  conversationSearch: byId("conversationSearch"),
  messageList: byId("messageList"),
  welcome: byId("welcomeState"),
  chatScroll: byId("chatScroll"),
  composer: byId("composerForm"),
  input: byId("messageInput"),
  send: byId("sendButton"),
  charCount: byId("characterCount"),
  model: byId("modelSelect"),
  persona: byId("personaSelect"),
  toolMode: byId("toolModeSelect"),
  providerName: byId("providerName"),
  providerHint: byId("providerHint"),
  providerDot: byId("providerDot"),
  sidebar: byId("sidebar"),
  backdrop: byId("sidebarBackdrop"),
  toastRegion: byId("toastRegion"),
  settingsDialog: byId("settingsDialog"),
  settingsForm: byId("settingsForm"),
  systemPrompt: byId("systemPromptInput"),
  systemPromptCount: byId("systemPromptCount"),
  statsDialog: byId("statsDialog"),
  statsGrid: byId("statsGrid"),
  providerBreakdown: byId("providerBreakdown"),
  planDialog: byId("planDialog"),
  planSummary: byId("planSummary"),
  planSteps: byId("planSteps"),
  taskTimeline: byId("taskTimeline"),
  emptyActivity: byId("emptyActivity"),
  attachmentStrip: byId("attachmentStrip"),
  fileInput: byId("fileInput"),
  artifactsDialog: byId("artifactsDialog"),
  artifactLibrary: byId("artifactLibrary"),
  recentArtifacts: byId("recentArtifacts"),
  artifactCount: byId("artifactCount"),
  contactsDialog: byId("contactsDialog"),
  contactList: byId("contactList"),
  contactForm: byId("contactForm"),
  contactImportInput: byId("contactImportInput"),
  whatsappDialog: byId("whatsappDialog"),
  confirmCheck: byId("confirmCheck"),
  confirmSend: byId("confirmSendButton"),
  recordingStrip: byId("recordingStrip"),
  recordingTime: byId("recordingTime"),
  voiceDialog: byId("voiceDialog"),
  voicePreview: byId("voicePreview"),
  transcriptInput: byId("transcriptInput"),
  voiceStatus: byId("voiceStatus"),
};

function requestHeaders(options) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = { ...(options.headers || {}) };
  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && state.config?.csrf_token) {
    headers["X-CSRF-Token"] = state.config.csrf_token;
  }
  return headers;
}

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: requestHeaders(options) });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const error = new Error(payload.error || `Request failed (${response.status})`);
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderInline(text) {
  return text
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(
      /\[([^\]]+)\]\(((?:https?:\/\/|\/api\/)[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
    );
}

function renderMarkdown(source) {
  const escaped = escapeHtml(source || "");
  const blocks = [];
  const text = escaped.replace(/```([\w+-]*)\n?([\s\S]*?)```/g, (_, language, code) => {
    const index = blocks.length;
    blocks.push(
      `<div class="code-block"><div class="code-header"><span>${language || "code"}</span>` +
      `<button class="copy-code" type="button">Copy</button></div><pre><code>${code.replace(/^\n|\n$/g, "")}</code></pre></div>`,
    );
    return `\n@@CODEBLOCK_${index}@@\n`;
  });
  const output = [];
  let listType = null;
  for (const rawLine of text.split("\n")) {
    const line = rawLine.trimEnd();
    const codeMatch = line.trim().match(/^@@CODEBLOCK_(\d+)@@$/);
    if (codeMatch) {
      if (listType) output.push(`</${listType}>`);
      listType = null;
      output.push(blocks[Number(codeMatch[1])]);
      continue;
    }
    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+\.\s+(.+)$/);
    if (unordered || ordered) {
      const needed = unordered ? "ul" : "ol";
      if (listType !== needed) {
        if (listType) output.push(`</${listType}>`);
        output.push(`<${needed}>`);
        listType = needed;
      }
      output.push(`<li>${renderInline((unordered || ordered)[1])}</li>`);
      continue;
    }
    if (listType) output.push(`</${listType}>`);
    listType = null;
    if (!line.trim()) output.push("");
    else if (line.startsWith("### ")) output.push(`<h3>${renderInline(line.slice(4))}</h3>`);
    else if (line.startsWith("## ")) output.push(`<h2>${renderInline(line.slice(3))}</h2>`);
    else if (line.startsWith("# ")) output.push(`<h1>${renderInline(line.slice(2))}</h1>`);
    else output.push(`<p>${renderInline(line)}</p>`);
  }
  if (listType) output.push(`</${listType}>`);
  return output.join("\n");
}

function formatTime(value) {
  if (!value) return "now";
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function formatNumber(value, maximumFractionDigits = 0) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits });
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

function toast(message, type = "info") {
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  els.toastRegion.appendChild(node);
  setTimeout(() => node.remove(), 3800);
}

function scrollToBottom(smooth = true) {
  requestAnimationFrame(() => {
    els.chatScroll.scrollTo({ top: els.chatScroll.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  });
}

function syncComposer() {
  els.input.style.height = "auto";
  els.input.style.height = `${Math.min(els.input.scrollHeight, 170)}px`;
  const max = state.config?.max_input_chars || 12000;
  els.charCount.textContent = `${els.input.value.length.toLocaleString()} / ${max.toLocaleString()}`;
  els.send.disabled = (!els.input.value.trim() && !state.streaming) || state.attachments.some((item) => item.uploading);
  els.send.classList.toggle("streaming", state.streaming);
  els.send.setAttribute("aria-label", state.streaming ? "Stop task" : "Send task");
}

function syncSystemPromptCount() {
  const max = state.config?.max_system_prompt_chars || 4000;
  els.systemPromptCount.textContent = `${els.systemPrompt.value.length.toLocaleString()} / ${max.toLocaleString()}`;
}

function closeSidebar() {
  els.sidebar.classList.remove("open");
  els.backdrop.classList.remove("open");
}

function openSidebar() {
  els.sidebar.classList.add("open");
  els.backdrop.classList.add("open");
}

function renderSidebar() {
  els.conversationList.replaceChildren();
  const query = state.search.trim().toLowerCase();
  const visible = state.conversations.filter((conversation) => (
    Boolean(conversation.is_archived) === state.showArchived &&
    conversation.title.toLowerCase().includes(query)
  ));
  if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "empty-list";
    empty.textContent = query
      ? "No conversations match this search."
      : state.showArchived
        ? "Archived conversations will appear here."
        : "Start a task and it will appear here.";
    els.conversationList.appendChild(empty);
    return;
  }
  visible.forEach((conversation) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `conversation-item${state.active?.id === conversation.id ? " active" : ""}`;
    button.dataset.id = conversation.id;
    button.innerHTML = `
      <span class="chat-icon" aria-hidden="true">◫</span>
      <span class="conversation-name">${escapeHtml(conversation.title)}</span>
      <span class="conversation-control pin-control${conversation.is_pinned ? " pinned" : ""}" title="${conversation.is_pinned ? "Unpin" : "Pin"}">★</span>
      <span class="conversation-control archive-control" title="${conversation.is_archived ? "Unarchive" : "Archive"}">${conversation.is_archived ? "↥" : "↧"}</span>
      <span class="conversation-control delete-control" title="Delete">×</span>`;
    button.addEventListener("click", (event) => {
      if (event.target.closest(".delete-control")) deleteConversation(conversation.id);
      else if (event.target.closest(".pin-control")) togglePin(conversation);
      else if (event.target.closest(".archive-control")) toggleArchive(conversation);
      else selectConversation(conversation.id);
    });
    els.conversationList.appendChild(button);
  });
}

function bindMessageActions(article, message) {
  article.querySelector(".copy-message")?.addEventListener("click", () => copyText(message.content));
  article.querySelector(".regenerate-message")?.addEventListener("click", regenerateLastResponse);
  article.querySelector(".reuse-message")?.addEventListener("click", () => {
    els.input.value = message.content;
    syncComposer();
    els.input.focus();
  });
  article.querySelectorAll(".copy-code").forEach((button) => {
    button.addEventListener("click", () => copyText(button.closest(".code-block").querySelector("code").textContent));
  });
}

function createMessageElement(message, pending = false) {
  const article = document.createElement("article");
  article.className = `message ${message.role}`;
  article.dataset.messageId = message.id || "pending";
  const isAssistant = message.role === "assistant";
  const stats = [
    message.model,
    message.output_tokens ? `${message.output_tokens} tokens` : null,
    message.latency_ms ? `${(message.latency_ms / 1000).toFixed(1)}s` : null,
  ].filter(Boolean).join(" · ");
  article.innerHTML = `
    <div class="avatar">${isAssistant ? "N" : "You"}</div>
    <div class="message-body">
      <div class="message-head">
        <span class="message-author">${isAssistant ? "NexaChat" : "You"}</span>
        <span class="message-time">${formatTime(message.created_at)}</span>
      </div>
      <div class="message-content">${renderMarkdown(message.content)}${pending ? '<span class="typing-cursor"></span>' : ""}</div>
      <div class="message-actions">
        <button class="message-action copy-message" type="button">Copy</button>
        ${isAssistant
          ? '<button class="message-action regenerate-message" type="button">Regenerate</button>'
          : '<button class="message-action reuse-message" type="button">Edit and resend</button>'}
        ${stats ? `<span class="message-stats">${escapeHtml(stats)}</span>` : ""}
      </div>
    </div>`;
  bindMessageActions(article, message);
  return article;
}

function syncPersonaSelect() {
  if (!state.active?.persona) return;
  const exists = [...els.persona.options].some((option) => option.value === state.active.persona);
  if (exists) els.persona.value = state.active.persona;
  else if (state.active.persona === "custom") {
    let custom = [...els.persona.options].find((option) => option.value === "custom");
    if (!custom) {
      custom = new Option("Custom", "custom");
      custom.disabled = true;
      els.persona.appendChild(custom);
    }
    els.persona.value = "custom";
  }
}

function renderConversation() {
  const messages = state.active?.messages || [];
  els.messageList.replaceChildren(...messages.map((message) => createMessageElement(message)));
  els.welcome.classList.toggle("hidden", messages.length > 0);
  els.conversationTitle.textContent = state.active?.title || "New task";
  if (state.active?.model) els.model.value = state.active.model;
  syncPersonaSelect();
  renderSidebar();
  scrollToBottom(false);
}

async function loadConversations() {
  state.conversations = await api("/api/conversations");
  renderSidebar();
}

async function selectConversation(id) {
  if (state.streaming) return toast("Stop the running task before switching.", "error");
  state.active = await api(`/api/conversations/${id}`);
  renderConversation();
  closeSidebar();
}

async function createConversation() {
  if (state.streaming) return;
  state.active = await api("/api/conversations", {
    method: "POST",
    body: JSON.stringify({
      model: els.model.value || state.config.default_model,
      persona: els.persona.value || "general",
    }),
  });
  await loadConversations();
  renderConversation();
  els.input.focus();
  closeSidebar();
}

async function deleteConversation(id) {
  if (!confirm("Delete this conversation permanently? Generated artifacts remain in your artifact workspace.")) return;
  try {
    await api(`/api/conversations/${id}`, { method: "DELETE" });
    state.conversations = state.conversations.filter((item) => item.id !== id);
    if (state.active?.id === id) state.active = null;
    renderConversation();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function togglePin(conversation) {
  try {
    await api(`/api/conversations/${conversation.id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_pinned: !conversation.is_pinned }),
    });
    await loadConversations();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function toggleArchive(conversation) {
  try {
    await api(`/api/conversations/${conversation.id}/${conversation.is_archived ? "unarchive" : "archive"}`, {
      method: "POST",
    });
    await loadConversations();
    if (state.active?.id === conversation.id) {
      state.active.is_archived = !conversation.is_archived;
      renderConversation();
    }
  } catch (error) {
    toast(error.message, "error");
  }
}

async function renameConversation() {
  if (!state.active) return;
  const title = prompt("Conversation title", state.active.title);
  if (!title?.trim()) return;
  try {
    state.active = await api(`/api/conversations/${state.active.id}`, {
      method: "PATCH",
      body: JSON.stringify({ title: title.trim() }),
    });
    await loadConversations();
    renderConversation();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function duplicateConversation() {
  if (!state.active || state.streaming) return toast("Open a conversation first.");
  try {
    state.active = await api(`/api/conversations/${state.active.id}/duplicate`, { method: "POST" });
    await loadConversations();
    renderConversation();
    toast("Conversation duplicated", "success");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Copied to clipboard", "success");
  } catch {
    toast("Clipboard access was unavailable.", "error");
  }
}

async function readSseResponse(response, onEvent) {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `Request failed (${response.status})`);
  }
  if (!response.body) throw new Error("Streaming is not supported by this browser.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      let eventName = "message";
      let eventData = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        if (line.startsWith("data:")) eventData += line.slice(5).trim();
      }
      if (eventData) await onEvent(eventName, JSON.parse(eventData));
    }
  }
}

async function streamChat(path, payload, assistantNode) {
  state.abortController = new AbortController();
  let fullText = "";
  let donePayload = null;
  const response = await fetch(path, {
    method: "POST",
    headers: requestHeaders({ method: "POST", headers: { Accept: "text/event-stream" }, body: "{}" }),
    body: JSON.stringify(payload),
    signal: state.abortController.signal,
  });
  await readSseResponse(response, (eventName, data) => {
    if (eventName === "delta") {
      fullText += data.text;
      assistantNode.querySelector(".message-content").innerHTML =
        `${renderMarkdown(fullText)}<span class="typing-cursor"></span>`;
      scrollToBottom(false);
    } else if (eventName === "done") {
      donePayload = data;
    } else if (eventName === "error") {
      throw new Error(data.message || "AI generation failed");
    }
  });
  return { fullText, donePayload };
}

function optimisticUserMessage(content) {
  const message = { role: "user", content, created_at: new Date().toISOString() };
  state.active.messages.push(message);
  els.welcome.classList.add("hidden");
  els.messageList.appendChild(createMessageElement(message));
  scrollToBottom();
  return message;
}

function clearComposerAfterSend() {
  els.input.value = "";
  state.attachments = [];
  renderAttachments();
  syncComposer();
}

async function sendMessage(content = null) {
  let message = (content ?? els.input.value).trim();
  if (!message || state.streaming) return;
  if (!state.active) await createConversation();
  if (els.toolMode.value === "research" && !/research|search|latest|current/i.test(message)) {
    message = `Research the web for: ${message}`;
  }
  if (els.toolMode.value !== "chat") {
    try {
      const result = await api("/api/plans", {
        method: "POST",
        body: JSON.stringify({
          conversation_id: state.active.id,
          goal: message,
          attachment_ids: state.attachments.filter((item) => item.id).map((item) => item.id),
        }),
      });
      if (result.mode === "plan") {
        optimisticUserMessage(message);
        clearComposerAfterSend();
        state.currentPlan = result.plan;
        showPlanDialog(result.plan);
        await loadConversations();
        return;
      }
    } catch (error) {
      toast(error.message, "error");
      return;
    }
  }
  await sendDirectChat(message);
}

async function sendDirectChat(message) {
  optimisticUserMessage(message);
  const pending = { role: "assistant", content: "", created_at: new Date().toISOString() };
  const assistantNode = createMessageElement(pending, true);
  els.messageList.appendChild(assistantNode);
  clearComposerAfterSend();
  state.streaming = true;
  syncComposer();
  try {
    const result = await streamChat(
      `/api/conversations/${state.active.id}/messages`,
      { content: message, model: els.model.value },
      assistantNode,
    );
    const stored = result.donePayload?.message || { ...pending, content: result.fullText };
    state.active.messages.push(stored);
    if (result.donePayload?.conversation) {
      state.active = { ...state.active, ...result.donePayload.conversation, messages: state.active.messages };
    }
    assistantNode.replaceWith(createMessageElement(stored));
    await loadConversations();
    maybeSpeak(stored.content);
  } catch (error) {
    if (error.name === "AbortError") {
      assistantNode.querySelector(".message-content").innerHTML = "<p><em>Generation stopped.</em></p>";
      toast("Generation stopped");
    } else {
      assistantNode.querySelector(".message-content").innerHTML =
        `<p><strong>Could not generate a response.</strong></p><p>${escapeHtml(error.message)}</p>`;
      toast(error.message, "error");
    }
  } finally {
    state.streaming = false;
    state.abortController = null;
    syncComposer();
    els.input.focus();
  }
}

function showPlanDialog(plan) {
  els.planSummary.innerHTML = `
    <div class="plan-fact"><span>Interpreted goal</span><strong>${escapeHtml(plan.goal)}</strong></div>
    <div class="plan-fact"><span>Expected output</span><strong>${escapeHtml(plan.expected_output)}</strong></div>
    <div class="plan-fact"><span>Required tools</span><strong>${escapeHtml(plan.required_tools.join(", ") || "No external tools")}</strong></div>
    <div class="plan-fact"><span>Confirmation</span><strong>${plan.confirmation_required ? "Required before external action" : "Approval to run this plan"}</strong></div>`;
  els.planSteps.innerHTML = plan.steps.map((step, index) => `
    <div class="plan-step">
      <span>${index + 1}</span>
      <b>${escapeHtml(step.label)}</b>
      <small>${escapeHtml(step.tool || "orchestrator")}</small>
    </div>`).join("");
  els.planDialog.showModal();
}

async function cancelCurrentPlan() {
  if (!state.currentPlan) return;
  try {
    await api(`/api/plans/${state.currentPlan.id}/cancel`, { method: "POST" });
    els.planDialog.close();
    toast("Task plan cancelled.");
    state.currentPlan = null;
  } catch (error) {
    toast(error.message, "error");
  }
}

function initializeTimeline(plan) {
  els.emptyActivity.classList.add("hidden");
  els.taskTimeline.classList.remove("hidden");
  els.taskTimeline.innerHTML = plan.steps.map((step) => `
    <div class="timeline-step" data-step-id="${escapeHtml(step.id)}">
      <span class="timeline-marker">·</span>
      <div class="timeline-copy"><strong>${escapeHtml(step.label)}</strong><small>Waiting</small></div>
    </div>`).join("");
}

function updateTimeline(data) {
  const node = els.taskTimeline.querySelector(`[data-step-id="${CSS.escape(data.step_id)}"]`);
  if (!node) return;
  node.classList.remove("running", "completed");
  node.classList.add(data.status);
  node.querySelector(".timeline-marker").textContent = data.status === "completed" ? "✓" : data.status === "running" ? "↻" : "·";
  node.querySelector("small").textContent = data.detail || data.status;
}

async function executeCurrentPlan() {
  if (!state.currentPlan || state.streaming) return;
  const plan = state.currentPlan;
  els.planDialog.close();
  initializeTimeline(plan);
  const pending = { role: "assistant", content: "", created_at: new Date().toISOString() };
  const assistantNode = createMessageElement(pending, true);
  els.messageList.appendChild(assistantNode);
  state.streaming = true;
  state.abortController = new AbortController();
  syncComposer();
  try {
    const response = await fetch(`/api/plans/${plan.id}/execute`, {
      method: "POST",
      headers: requestHeaders({ method: "POST", headers: { Accept: "text/event-stream" }, body: "{}" }),
      body: "{}",
      signal: state.abortController.signal,
    });
    let donePayload = null;
    await readSseResponse(response, (eventName, data) => {
      if (eventName === "progress") {
        updateTimeline(data);
        assistantNode.querySelector(".message-content").innerHTML =
          `<p><em>${escapeHtml(data.detail)}</em></p><span class="typing-cursor"></span>`;
        scrollToBottom(false);
      } else if (eventName === "done") {
        donePayload = data;
      } else if (eventName === "error") {
        throw new Error(data.message || "Task execution failed");
      }
    });
    if (!donePayload?.message) throw new Error("Task finished without a persisted result");
    state.active.messages.push(donePayload.message);
    assistantNode.replaceWith(createMessageElement(donePayload.message));
    if (donePayload.artifacts?.length) {
      state.artifacts = [...donePayload.artifacts, ...state.artifacts.filter((item) => !donePayload.artifacts.some((newItem) => newItem.id === item.id))];
      renderRecentArtifacts();
    }
    if (donePayload.whatsapp) showWhatsAppConfirmation(donePayload.whatsapp);
    await Promise.all([loadConversations(), loadArtifacts()]);
    maybeSpeak(donePayload.message.content);
    toast(donePayload.whatsapp ? "Action prepared for confirmation." : "Task completed.", "success");
  } catch (error) {
    if (error.name === "AbortError") {
      assistantNode.querySelector(".message-content").innerHTML = "<p><em>Task stream stopped. Check Task history before retrying.</em></p>";
    } else {
      assistantNode.querySelector(".message-content").innerHTML =
        `<p><strong>Task failed safely.</strong></p><p>${escapeHtml(error.message)}</p>`;
      toast(error.message, "error");
    }
  } finally {
    state.streaming = false;
    state.abortController = null;
    state.currentPlan = null;
    syncComposer();
  }
}

async function regenerateLastResponse() {
  if (!state.active || state.streaming) return;
  const lastIndex = [...state.active.messages].map((message) => message.role).lastIndexOf("assistant");
  if (lastIndex < 0) return;
  const previous = state.active.messages[lastIndex];
  if (previous.provider === "tool-orchestrator") {
    return toast("Tool results are regenerated by resubmitting the original task so a new plan can be reviewed.");
  }
  state.active.messages.splice(lastIndex, 1);
  renderConversation();
  const pending = { role: "assistant", content: "", created_at: new Date().toISOString() };
  const node = createMessageElement(pending, true);
  els.messageList.appendChild(node);
  state.streaming = true;
  syncComposer();
  try {
    const result = await streamChat(`/api/conversations/${state.active.id}/regenerate`, { model: els.model.value }, node);
    if (result.donePayload?.message) {
      state.active.messages.push(result.donePayload.message);
      node.replaceWith(createMessageElement(result.donePayload.message));
      await loadConversations();
    }
  } catch (error) {
    state.active.messages.push(previous);
    node.replaceWith(createMessageElement(previous));
    toast(error.message, "error");
  } finally {
    state.streaming = false;
    state.abortController = null;
    syncComposer();
  }
}

function renderAttachments() {
  els.attachmentStrip.replaceChildren();
  state.attachments.forEach((attachment) => {
    const chip = document.createElement("div");
    chip.className = `attachment-chip${attachment.uploading ? " uploading" : ""}`;
    chip.innerHTML = `<b>${attachment.uploading ? "↻" : "✓"}</b><span>${escapeHtml(attachment.name)}</span><small>${attachment.progress ?? 100}%</small><button type="button" aria-label="Remove attachment">×</button>`;
    chip.querySelector("button").addEventListener("click", () => {
      if (attachment.uploading) return;
      state.attachments = state.attachments.filter((item) => item.localId !== attachment.localId);
      renderAttachments();
      syncComposer();
    });
    els.attachmentStrip.appendChild(chip);
  });
}

function uploadWithProgress(file) {
  return new Promise((resolve, reject) => {
    const localId = crypto.randomUUID();
    const attachment = { localId, name: file.name, uploading: true, progress: 0 };
    state.attachments.push(attachment);
    renderAttachments();
    syncComposer();
    const formData = new FormData();
    formData.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/uploads");
    xhr.setRequestHeader("X-CSRF-Token", state.config.csrf_token);
    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      attachment.progress = Math.round((event.loaded / event.total) * 100);
      renderAttachments();
    });
    xhr.addEventListener("load", () => {
      let payload = {};
      try { payload = JSON.parse(xhr.responseText || "{}"); } catch { /* no-op */ }
      if (xhr.status >= 200 && xhr.status < 300) {
        Object.assign(attachment, payload, { localId, uploading: false, progress: 100 });
        renderAttachments();
        syncComposer();
        resolve(payload);
      } else {
        state.attachments = state.attachments.filter((item) => item.localId !== localId);
        renderAttachments();
        syncComposer();
        reject(new Error(payload.error || `Upload failed (${xhr.status})`));
      }
    });
    xhr.addEventListener("error", () => {
      state.attachments = state.attachments.filter((item) => item.localId !== localId);
      renderAttachments();
      syncComposer();
      reject(new Error("Upload connection failed"));
    });
    xhr.send(formData);
  });
}

async function uploadSelectedFiles(files) {
  for (const file of files) {
    try {
      await uploadWithProgress(file);
      toast(`${file.name} uploaded securely.`, "success");
    } catch (error) {
      toast(`${file.name}: ${error.message}`, "error");
    }
  }
  els.fileInput.value = "";
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    return toast("Voice recording is not supported in this browser.", "error");
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    state.recorder = recorder;
    state.recordingChunks = [];
    state.cancelRecording = false;
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size) state.recordingChunks.push(event.data);
    });
    recorder.addEventListener("stop", async () => {
      stream.getTracks().forEach((track) => track.stop());
      clearInterval(state.recordingTimer);
      els.recordingStrip.classList.add("hidden");
      if (state.cancelRecording) return;
      const type = recorder.mimeType || "audio/webm";
      const extension = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm";
      const blob = new Blob(state.recordingChunks, { type });
      const file = new File([blob], `voice-${Date.now()}.${extension}`, { type });
      try {
        const upload = await uploadWithProgress(file);
        state.voiceUpload = upload;
        els.voicePreview.src = URL.createObjectURL(blob);
        els.transcriptInput.value = "";
        els.voiceStatus.textContent = "The recording is attached. Transcribe it for review, or keep the original audio for a confirmed media action.";
        els.voiceDialog.showModal();
      } catch (error) {
        toast(error.message, "error");
      }
    });
    recorder.start(250);
    state.recordingStartedAt = Date.now();
    els.recordingStrip.classList.remove("hidden");
    state.recordingTimer = setInterval(updateRecordingTime, 250);
    updateRecordingTime();
  } catch (error) {
    toast(`Microphone access failed: ${error.message}`, "error");
  }
}

function updateRecordingTime() {
  const seconds = Math.floor((Date.now() - state.recordingStartedAt) / 1000);
  els.recordingTime.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function pauseResumeRecording() {
  if (!state.recorder) return;
  if (state.recorder.state === "recording") {
    state.recorder.pause();
    byId("pauseRecordingButton").textContent = "Resume";
  } else if (state.recorder.state === "paused") {
    state.recorder.resume();
    byId("pauseRecordingButton").textContent = "Pause";
  }
}

function stopRecording(cancel = false) {
  if (!state.recorder || state.recorder.state === "inactive") return;
  state.cancelRecording = cancel;
  state.recorder.stop();
  state.recorder = null;
  byId("pauseRecordingButton").textContent = "Pause";
}

async function transcribeVoice() {
  if (!state.voiceUpload) return;
  byId("transcribeButton").disabled = true;
  els.voiceStatus.textContent = "Transcribing securely…";
  try {
    const result = await api(`/api/uploads/${state.voiceUpload.id}/transcribe`, { method: "POST" });
    els.transcriptInput.value = result.transcript;
    els.voiceStatus.textContent = "Review and edit the transcript before using it as a command.";
  } catch (error) {
    els.voiceStatus.textContent = error.message;
    toast(error.message, "error");
  } finally {
    byId("transcribeButton").disabled = false;
  }
}

function useTranscript() {
  const text = els.transcriptInput.value.trim();
  if (!text) return toast("Transcribe or enter a command first.", "error");
  els.input.value = text;
  els.voiceDialog.close();
  syncComposer();
  els.input.focus();
}

async function loadArtifacts(kind = "") {
  state.artifacts = await api(`/api/artifacts${kind ? `?kind=${encodeURIComponent(kind)}` : ""}`);
  els.artifactCount.textContent = state.artifacts.length;
  renderRecentArtifacts();
  if (els.artifactsDialog.open) renderArtifactLibrary();
}

function renderRecentArtifacts() {
  if (!state.artifacts.length) {
    els.recentArtifacts.innerHTML = '<p class="rail-empty">Generated files will appear here.</p>';
    return;
  }
  els.recentArtifacts.innerHTML = state.artifacts.slice(0, 4).map((artifact) => `
    <a class="rail-artifact" href="${artifact.download_url}">
      <span class="file-type">${escapeHtml(artifact.kind.slice(0, 3))}</span>
      <span><b>${escapeHtml(artifact.name)}</b><small>${formatBytes(artifact.size_bytes)} · ${formatTime(artifact.created_at)}</small></span>
      <span>⇩</span>
    </a>`).join("");
}

function artifactPreviewText(artifact) {
  if (artifact.preview?.columns) return `${artifact.preview.columns.length} columns · ${artifact.preview.rows?.length || 0} preview rows`;
  if (artifact.preview?.slides) return `${artifact.preview.slides.length} slides · ${artifact.preview.theme || "custom"} theme`;
  if (artifact.preview?.sections) return `${artifact.preview.sections.length} sections · ${artifact.preview.source_count || 0} sources`;
  return `${artifact.kind} artifact · ${formatBytes(artifact.size_bytes)}`;
}

function artifactPreviewHtml(artifact) {
  const columns = artifact.preview?.columns?.slice(0, 6);
  const rows = artifact.preview?.rows?.slice(0, 5);
  if (!columns?.length || !rows?.length) return "";
  return `
    <div class="artifact-table-wrap" tabindex="0" aria-label="Spreadsheet preview">
      <table>
        <thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(row[column] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>
    </div>`;
}

function renderArtifactLibrary() {
  if (!state.artifacts.length) {
    els.artifactLibrary.innerHTML = '<div class="empty-library">No artifacts match this filter.</div>';
    return;
  }
  els.artifactLibrary.innerHTML = state.artifacts.map((artifact) => `
    <article class="artifact-card" data-artifact-id="${artifact.id}">
      <div class="artifact-card-head">
        <span class="file-type">${escapeHtml(artifact.kind.slice(0, 3))}</span>
        <div><h3 title="${escapeHtml(artifact.name)}">${escapeHtml(artifact.name)}</h3><small>${formatBytes(artifact.size_bytes)} · ${new Date(artifact.created_at).toLocaleDateString()}</small></div>
        <button class="message-action rename-artifact" type="button">Rename</button>
      </div>
      <p>${escapeHtml(artifactPreviewText(artifact))}</p>
      ${artifactPreviewHtml(artifact)}
      <div class="artifact-actions">
        <a href="${artifact.download_url}">Download</a>
        ${artifact.kind !== "pdf" ? '<button type="button" data-convert="pdf">To PDF</button>' : ""}
        ${artifact.kind !== "word" ? '<button type="button" data-convert="word">To Word</button>' : ""}
        ${artifact.kind !== "powerpoint" ? '<button type="button" data-convert="powerpoint">To slides</button>' : ""}
        ${["pdf", "word", "powerpoint", "excel"].includes(artifact.kind) ? `<button type="button" data-convert="${escapeHtml(artifact.kind)}">Regenerate</button>` : ""}
        <button class="delete-artifact" type="button">Delete</button>
      </div>
    </article>`).join("");
  els.artifactLibrary.querySelectorAll(".artifact-card").forEach((card) => {
    const artifact = state.artifacts.find((item) => item.id === card.dataset.artifactId);
    card.querySelector(".rename-artifact").addEventListener("click", () => renameArtifact(artifact));
    card.querySelector(".delete-artifact").addEventListener("click", () => deleteArtifact(artifact));
    card.querySelectorAll("[data-convert]").forEach((button) => {
      button.addEventListener("click", () => convertArtifact(artifact, button.dataset.convert));
    });
  });
}

async function openArtifacts(kind = "") {
  els.artifactLibrary.innerHTML = '<div class="loading-state">Loading artifacts…</div>';
  els.artifactsDialog.showModal();
  try {
    await loadArtifacts(kind);
    renderArtifactLibrary();
  } catch (error) {
    els.artifactLibrary.innerHTML = `<div class="empty-library">${escapeHtml(error.message)}</div>`;
  }
}

async function renameArtifact(artifact) {
  const name = prompt("Artifact name", artifact.name);
  if (!name?.trim()) return;
  try {
    await api(`/api/artifacts/${artifact.id}`, { method: "PATCH", body: JSON.stringify({ name: name.trim() }) });
    await loadArtifacts();
    renderArtifactLibrary();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function deleteArtifact(artifact) {
  if (!confirm(`Delete ${artifact.name}? The stored file will be removed.`)) return;
  try {
    await api(`/api/artifacts/${artifact.id}`, { method: "DELETE" });
    await loadArtifacts();
    renderArtifactLibrary();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function convertArtifact(artifact, format) {
  try {
    toast(format === artifact.kind ? `Regenerating ${artifact.name}…` : `Converting to ${format}…`);
    const created = await api(`/api/artifacts/${artifact.id}/convert`, {
      method: "POST",
      body: JSON.stringify({ format }),
    });
    await loadArtifacts();
    renderArtifactLibrary();
    toast(`${created.name} is ready.`, "success");
  } catch (error) {
    toast(error.message, "error");
  }
}

function resetContactForm() {
  els.contactForm.reset();
  byId("contactId").value = "";
}

async function loadContacts() {
  const query = byId("contactSearch").value.trim();
  const contacts = await api(`/api/contacts${query ? `?q=${encodeURIComponent(query)}` : ""}`);
  if (!contacts.length) {
    els.contactList.innerHTML = '<div class="empty-library">No contacts found.</div>';
    return;
  }
  els.contactList.innerHTML = contacts.map((contact) => `
    <article class="contact-row" data-contact-id="${contact.id}">
      <div><b>${escapeHtml(contact.name)}</b><small>${escapeHtml(contact.phone_masked)}${contact.relationship ? ` · ${escapeHtml(contact.relationship)}` : ""}</small></div>
      <div><button class="edit-contact" type="button">Edit</button><button class="delete-contact" type="button">Delete</button></div>
    </article>`).join("");
  els.contactList.querySelectorAll(".contact-row").forEach((row) => {
    row.querySelector(".edit-contact").addEventListener("click", () => editContact(row.dataset.contactId));
    row.querySelector(".delete-contact").addEventListener("click", () => deleteContact(row.dataset.contactId));
  });
}

async function openContacts() {
  els.contactsDialog.showModal();
  resetContactForm();
  try { await loadContacts(); } catch (error) { toast(error.message, "error"); }
}

async function saveContact(event) {
  event.preventDefault();
  const id = byId("contactId").value;
  const payload = {
    name: byId("contactName").value,
    phone: byId("contactPhone").value,
    email: byId("contactEmail").value,
    relationship: byId("contactRelationship").value,
    notes: byId("contactNotes").value,
  };
  try {
    await api(id ? `/api/contacts/${id}` : "/api/contacts", {
      method: id ? "PATCH" : "POST",
      body: JSON.stringify(payload),
    });
    resetContactForm();
    await loadContacts();
    toast("Contact saved.", "success");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function editContact(id) {
  try {
    const contact = await api(`/api/contacts/${id}`);
    byId("contactId").value = contact.id;
    byId("contactName").value = contact.name || "";
    byId("contactPhone").value = contact.phone || "";
    byId("contactEmail").value = contact.email || "";
    byId("contactRelationship").value = contact.relationship || "";
    byId("contactNotes").value = contact.notes || "";
  } catch (error) {
    toast(error.message, "error");
  }
}

async function deleteContact(id) {
  if (!confirm("Delete this contact?")) return;
  try {
    await api(`/api/contacts/${id}`, { method: "DELETE" });
    await loadContacts();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function importContacts() {
  const file = els.contactImportInput.files[0];
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  try {
    const result = await api("/api/contacts/import", { method: "POST", body });
    await loadContacts();
    const skipped = result.skipped?.length || 0;
    toast(
      `Imported ${result.created} contact${result.created === 1 ? "" : "s"}${skipped ? `; skipped ${skipped}` : ""}.`,
      skipped ? "info" : "success",
    );
  } catch (error) {
    toast(error.message, "error");
  } finally {
    els.contactImportInput.value = "";
  }
}

function showWhatsAppConfirmation(payload) {
  state.whatsapp = payload;
  byId("confirmRecipient").textContent = payload.contact_name;
  byId("confirmPhone").textContent = payload.recipient_masked;
  byId("confirmType").textContent = payload.message_type === "audio" ? "Original audio message" : "Text message";
  byId("confirmBody").textContent = payload.body || "The attached original audio recording";
  byId("confirmMode").textContent = payload.mode === "mock" ? "Sandbox / mock (no real message)" : "Meta WhatsApp Cloud API";
  els.confirmCheck.checked = false;
  els.confirmSend.disabled = true;
  els.whatsappDialog.showModal();
}

async function confirmWhatsAppSend() {
  if (!state.whatsapp || !els.confirmCheck.checked) return;
  els.confirmSend.disabled = true;
  els.confirmSend.textContent = "Sending…";
  try {
    const result = await api(`/api/whatsapp/${state.whatsapp.id}/confirm-send`, {
      method: "POST",
      body: JSON.stringify({ confirmation_token: state.whatsapp.confirmation_token }),
    });
    els.whatsappDialog.close();
    state.whatsapp = null;
    toast(`WhatsApp provider status: ${result.status}`, "success");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    els.confirmSend.textContent = "Confirm and send";
    els.confirmSend.disabled = !els.confirmCheck.checked;
  }
}

function renderAccount(user) {
  const registered = Boolean(user && !user.is_guest);
  byId("accountStatus").textContent = registered
    ? `${user.display_name} · ${user.email}`
    : state.config?.auth_required
      ? "Sign in or create an account to continue"
      : "Guest workspace · sign in to keep a named account";
  byId("accountFields").classList.toggle("hidden", registered);
  byId("loginButton").classList.toggle("hidden", registered);
  byId("registerButton").classList.toggle("hidden", registered);
  byId("logoutButton").classList.toggle("hidden", !registered);
  byId("workspaceSettingsFields").classList.toggle(
    "hidden",
    Boolean(state.config?.auth_required && !registered),
  );
}

function renderProviderConfiguration() {
  byId("providerConfigStatus").textContent =
    `AI: ${state.config.provider} · Search: ${state.config.search_provider} · WhatsApp: ${state.config.whatsapp_mode}`;
}

async function authenticate(mode) {
  const email = byId("accountEmail").value.trim();
  const password = byId("accountPassword").value;
  const displayName = byId("accountName").value.trim();
  if (!email || !password) return toast("Enter your email and password.", "error");
  try {
    const result = await api(`/api/auth/${mode}`, {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        ...(mode === "register" ? { display_name: displayName } : {}),
      }),
    });
    state.config.csrf_token = result.csrf_token;
    window.location.reload();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST", body: "{}" });
    window.location.reload();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function openSettings() {
  try {
    state.user = await api("/api/auth/me");
    renderAccount(state.user);
    if (!(state.config.auth_required && state.user?.is_guest)) {
      state.preferences = await api("/api/preferences");
      els.systemPrompt.value = state.active?.system_prompt || "";
      byId("languagePreference").value = state.preferences.language;
      byId("themePreference").value = state.preferences.presentation_theme;
      byId("autoSpeakPreference").checked = state.preferences.auto_speak;
    }
    syncSystemPromptCount();
    els.settingsDialog.showModal();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function saveSettings(event) {
  event.preventDefault();
  try {
    const systemPrompt = els.systemPrompt.value.trim();
    if (systemPrompt && state.active) {
      state.active = await api(`/api/conversations/${state.active.id}`, {
        method: "PATCH",
        body: JSON.stringify({ system_prompt: systemPrompt }),
      });
    }
    state.preferences = await api("/api/preferences", {
      method: "PATCH",
      body: JSON.stringify({
        language: byId("languagePreference").value,
        presentation_theme: byId("themePreference").value,
        auto_speak: byId("autoSpeakPreference").checked,
      }),
    });
    els.settingsDialog.close();
    if (state.active) renderConversation();
    toast("Workspace settings saved.", "success");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function resetInstructions() {
  if (!state.active) return;
  try {
    state.active = await api(`/api/conversations/${state.active.id}`, {
      method: "PATCH",
      body: JSON.stringify({ persona: els.persona.value === "custom" ? "general" : els.persona.value }),
    });
    els.systemPrompt.value = state.active.system_prompt;
    syncSystemPromptCount();
    toast("Conversation instructions reset.");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function clearMemory() {
  if (!confirm("Delete all saved workspace memory preferences?")) return;
  try {
    await api("/api/preferences/memory", { method: "DELETE" });
    toast("Saved memory deleted.", "success");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function openStats() {
  els.statsGrid.innerHTML = '<div class="loading-state">Loading measured workspace analytics…</div>';
  els.providerBreakdown.replaceChildren();
  els.statsDialog.showModal();
  try {
    const stats = await api("/api/analytics");
    const cards = [
      ["Conversations", stats.conversations],
      ["Artifacts", stats.artifacts],
      ["Tool calls", stats.tool_calls],
      ["Web searches", stats.web_searches],
      ["Successful tasks", stats.successful_tasks],
      ["Failed tasks", stats.failed_tasks],
      ["Avg tool latency", stats.average_tool_latency_ms ? `${formatNumber(stats.average_tool_latency_ms)} ms` : "—"],
      ["Estimated cost", `$${Number(stats.estimated_ai_cost_usd || 0).toFixed(4)}`],
      ["Pending confirms", stats.pending_confirmations],
    ];
    els.statsGrid.innerHTML = cards.map(([label, value]) =>
      `<article class="stat-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`,
    ).join("");
    els.providerBreakdown.innerHTML = stats.most_used_tools.length
      ? `<h3>Most-used tools</h3>${stats.most_used_tools.map(([tool, count]) =>
          `<div class="provider-row"><span>${escapeHtml(tool)}</span><strong>${formatNumber(count)} calls</strong></div>`).join("")}`
      : "<p>No tool calls have been measured yet.</p>";
  } catch (error) {
    els.statsGrid.innerHTML = `<div class="loading-state">${escapeHtml(error.message)}</div>`;
  }
}

async function exportConversation() {
  if (!state.active?.messages?.length) return toast("There is no conversation to export.");
  try {
    const artifact = await api(`/api/conversations/${state.active.id}/artifact-export`, {
      method: "POST",
      body: JSON.stringify({ format: "markdown" }),
    });
    await loadArtifacts();
    window.location.assign(artifact.download_url);
  } catch (error) {
    toast(error.message, "error");
  }
}

async function maybeSpeak(text) {
  if (!state.preferences?.auto_speak || !text) return;
  try {
    const artifact = await api("/api/speech", {
      method: "POST",
      body: JSON.stringify({ text: text.replace(/[#*_`\[\]()]/g, "").slice(0, 2500) }),
    });
    const audio = new Audio(artifact.download_url);
    await audio.play();
    await loadArtifacts();
  } catch (error) {
    toast(`Spoken response unavailable: ${error.message}`, "error");
  }
}

function setupEvents() {
  els.composer.addEventListener("submit", (event) => {
    event.preventDefault();
    if (state.streaming) state.abortController?.abort();
    else sendMessage();
  });
  els.input.addEventListener("input", syncComposer);
  els.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendMessage();
    }
  });
  byId("commandInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.value.trim()) {
      els.input.value = event.target.value;
      event.target.value = "";
      syncComposer();
      sendMessage();
    }
  });
  els.conversationSearch.addEventListener("input", () => {
    state.search = els.conversationSearch.value;
    renderSidebar();
  });
  byId("archiveFilterButton").addEventListener("click", (event) => {
    state.showArchived = !state.showArchived;
    event.currentTarget.setAttribute("aria-pressed", String(state.showArchived));
    renderSidebar();
  });
  byId("newChatButton").addEventListener("click", createConversation);
  byId("clearAllButton").addEventListener("click", async () => {
    if (!state.conversations.length || !confirm("Delete all conversations permanently? Artifacts are kept separately.")) return;
    try {
      await api("/api/conversations", { method: "DELETE" });
      state.active = null;
      state.conversations = [];
      renderConversation();
    } catch (error) {
      toast(error.message, "error");
    }
  });
  els.conversationTitle.addEventListener("click", renameConversation);
  byId("exportButton").addEventListener("click", exportConversation);
  byId("duplicateButton").addEventListener("click", duplicateConversation);
  byId("settingsButton").addEventListener("click", openSettings);
  byId("statsButton").addEventListener("click", openStats);
  byId("artifactsButton").addEventListener("click", () => openArtifacts());
  byId("viewAllArtifactsButton").addEventListener("click", () => openArtifacts());
  byId("contactsButton").addEventListener("click", openContacts);
  byId("approvePlanButton").addEventListener("click", executeCurrentPlan);
  byId("cancelPlanButton").addEventListener("click", cancelCurrentPlan);
  byId("attachButton").addEventListener("click", () => els.fileInput.click());
  els.fileInput.addEventListener("change", () => uploadSelectedFiles([...els.fileInput.files]));
  byId("voiceButton").addEventListener("click", startRecording);
  byId("pauseRecordingButton").addEventListener("click", pauseResumeRecording);
  byId("stopRecordingButton").addEventListener("click", () => stopRecording(false));
  byId("cancelRecordingButton").addEventListener("click", () => stopRecording(true));
  byId("transcribeButton").addEventListener("click", transcribeVoice);
  byId("useTranscriptButton").addEventListener("click", useTranscript);
  byId("useOriginalAudioButton").addEventListener("click", () => {
    els.voiceDialog.close();
    els.input.focus();
    toast("Original audio kept as an attachment. Describe the action before sending.");
  });
  els.contactForm.addEventListener("submit", saveContact);
  byId("resetContactButton").addEventListener("click", resetContactForm);
  byId("importContactsButton").addEventListener("click", () => els.contactImportInput.click());
  els.contactImportInput.addEventListener("change", importContacts);
  byId("contactSearch").addEventListener("input", () => loadContacts().catch((error) => toast(error.message, "error")));
  els.confirmCheck.addEventListener("change", () => { els.confirmSend.disabled = !els.confirmCheck.checked; });
  els.confirmSend.addEventListener("click", confirmWhatsAppSend);
  els.settingsForm.addEventListener("submit", saveSettings);
  byId("loginButton").addEventListener("click", () => authenticate("login"));
  byId("registerButton").addEventListener("click", () => authenticate("register"));
  byId("logoutButton").addEventListener("click", logout);
  els.systemPrompt.addEventListener("input", syncSystemPromptCount);
  byId("resetInstructionsButton").addEventListener("click", resetInstructions);
  byId("clearMemoryButton").addEventListener("click", clearMemory);
  byId("themeButton").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("nexachat-theme", next);
  });
  byId("openSidebar").addEventListener("click", openSidebar);
  byId("closeSidebar").addEventListener("click", closeSidebar);
  els.backdrop.addEventListener("click", closeSidebar);
  els.model.addEventListener("change", async () => {
    if (!state.active) return;
    try {
      state.active = await api(`/api/conversations/${state.active.id}`, {
        method: "PATCH",
        body: JSON.stringify({ model: els.model.value }),
      });
      await loadConversations();
    } catch (error) {
      toast(error.message, "error");
    }
  });
  els.persona.addEventListener("change", async () => {
    if (!state.active || els.persona.value === "custom") return;
    try {
      state.active = await api(`/api/conversations/${state.active.id}`, {
        method: "PATCH",
        body: JSON.stringify({ persona: els.persona.value }),
      });
      renderConversation();
      toast("Persona updated.", "success");
    } catch (error) {
      toast(error.message, "error");
    }
  });
  document.querySelectorAll(".prompt-card").forEach((card) => {
    card.addEventListener("click", () => sendMessage(card.dataset.prompt));
  });
  document.querySelectorAll("[data-close]").forEach((button) => {
    button.addEventListener("click", () => byId(button.dataset.close).close());
  });
  document.querySelectorAll("[data-artifact-filter]").forEach((button) => {
    button.addEventListener("click", async () => {
      document.querySelectorAll("[data-artifact-filter]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      await loadArtifacts(button.dataset.artifactFilter);
      renderArtifactLibrary();
    });
  });
  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      createConversation();
    }
    if (event.key === "Escape" && state.streaming) state.abortController?.abort();
  });
}

async function init() {
  document.documentElement.dataset.theme = localStorage.getItem("nexachat-theme") || "dark";
  setupEvents();
  syncComposer();
  try {
    state.config = await api("/api/config");
    renderProviderConfiguration();
    els.model.innerHTML = state.config.models.map((model) =>
      `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`).join("");
    els.model.value = state.config.default_model;
    els.persona.innerHTML = state.config.personas.map((persona) =>
      `<option value="${escapeHtml(persona.id)}">${escapeHtml(persona.label)}</option>`).join("");
    els.input.maxLength = state.config.max_input_chars;
    els.systemPrompt.maxLength = state.config.max_system_prompt_chars;
    const provider = state.config.provider;
    els.providerName.textContent = provider === "openai"
      ? "OpenAI connected"
      : provider === "ollama"
        ? "Ollama connected"
        : "Demo mode";
    const research = state.config.search_provider === "demo" ? "research off" : `${state.config.search_provider} search`;
    els.providerHint.textContent = `${provider} · ${research} · WhatsApp ${state.config.whatsapp_mode}`;
    els.providerDot.classList.toggle("demo", provider === "demo");
    state.user = await api("/api/auth/me");
    if (state.config.auth_required && state.user?.is_guest) {
      renderAccount(state.user);
      els.providerName.textContent = "Sign-in required";
      els.providerHint.textContent = "Open Workspace settings to authenticate";
      els.settingsDialog.showModal();
      return;
    }
    await Promise.all([loadConversations(), loadArtifacts(), api("/api/preferences").then((value) => { state.preferences = value; })]);
  } catch (error) {
    toast(`Startup failed: ${error.message}`, "error");
    els.providerName.textContent = "Backend unavailable";
    els.providerHint.textContent = "Check the service health";
    els.providerDot.classList.add("demo");
  }
  els.input.focus();
}

init();
