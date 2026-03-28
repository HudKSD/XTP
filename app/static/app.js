const state = {
  chats: [],
  currentChatId: null,
  ws: null,
  wsGeneration: 0,
  wsReconnectTimer: null,
  wsReconnectAttempts: 0,
  wsHeartbeatTimer: null,
  wsLastPongAt: 0,
  wsManualClose: false,
  pendingOutbound: null,
  pendingAssistantElement: null,
  terminalVisible: true,
  busy: false,
  activeTooltipAnchor: null,
  modalResolver: null,
  modalMode: null,
  historyFilter: "",
  planMode: false,
  rightPaneMode: "console",
  pendingToolEvents: [],
  lastUserPrompt: "",
  activity: {
    phase: "Idle",
    toolCount: 0,
    lastEvent: "Workspace ready",
  },
};

const shellEl = document.getElementById("appShell");
const chatListEl = document.getElementById("chatList");
const historySearchInputEl = document.getElementById("historySearchInput");
const historyCountPillEl = document.getElementById("historyCountPill");
const chatWindowEl = document.getElementById("chatWindow");
const chatTitleEl = document.getElementById("chatTitle");
const composerInputEl = document.getElementById("composerInput");
const sendBtnEl = document.getElementById("sendBtn");
const newChatBtnEl = document.getElementById("newChatBtn");
const renameCurrentChatBtnEl = document.getElementById("renameCurrentChatBtn");
const statusBarEl = document.getElementById("statusBar");
const statusTextEl = document.getElementById("statusText");
const terminalOutputEl = document.getElementById("terminalOutput");
const toggleTerminalBtnEl = document.getElementById("toggleTerminalBtn");
const clearTerminalBtnEl = document.getElementById("clearTerminalBtn");
const consoleTabBtnEl = document.getElementById("consoleTabBtn");
const inspectorTabBtnEl = document.getElementById("inspectorTabBtn");
const consolePaneEl = document.getElementById("consolePane");
const inspectorPaneEl = document.getElementById("inspectorPane");
const inspectorCountPillEl = document.getElementById("inspectorCountPill");
const inspectorFlagsEl = document.getElementById("inspectorFlags");
const inspectorQueryEl = document.getElementById("inspectorQuery");
const inspectorToolsEl = document.getElementById("inspectorTools");
const messageTemplate = document.getElementById("messageTemplate");
const phaseCardEl = document.getElementById("phaseCard");
const toolCountCardEl = document.getElementById("toolCountCard");
const lastEventCardEl = document.getElementById("lastEventCard");
const promptChipEls = Array.from(document.querySelectorAll(".prompt-chip"));
const tooltipEl = document.getElementById("tooltipEl");
const toastHostEl = document.getElementById("toastHost");
const modalRootEl = document.getElementById("modalRoot");
const modalBodyEl = document.getElementById("modalBody");
const modalTitleEl = document.getElementById("modalTitle");
const modalCloseBtnEl = document.getElementById("modalCloseBtn");
const modalInputWrapEl = document.getElementById("modalInputWrap");
const modalInputEl = document.getElementById("modalInput");
const modalCancelBtnEl = document.getElementById("modalCancelBtn");
const modalConfirmBtnEl = document.getElementById("modalConfirmBtn");

function safeEscape(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmtDate(value) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value || "";
  return d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function fmtTime(value) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function fmtDayKey(value) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "unknown";
  const year = d.getFullYear();
  const month = `${d.getMonth() + 1}`.padStart(2, "0");
  const day = `${d.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function fmtDayLabel(value) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "Unknown date";
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(d);
  target.setHours(0, 0, 0, 0);
  const diffDays = Math.round((today - target) / 86400000);

  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays > 1 && diffDays < 7) return d.toLocaleDateString([], { weekday: "long" });
  return d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

function fmtRelativeShort(value) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  const diffMs = Date.now() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function autoGrowTextarea() {
  composerInputEl.style.height = "auto";
  composerInputEl.style.height = `${Math.min(composerInputEl.scrollHeight, 220)}px`;
}

function isNearBottom(container, threshold = 72) {
  return container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
}

function scrollChatToBottom(force = false) {
  if (force || isNearBottom(chatWindowEl)) {
    chatWindowEl.scrollTop = chatWindowEl.scrollHeight;
  }
}

function scrollTerminalToBottom(force = false) {
  if (force || isNearBottom(terminalOutputEl, 140)) {
    terminalOutputEl.scrollTop = terminalOutputEl.scrollHeight;
  }
}

function setBusy(value) {
  state.busy = value;
  sendBtnEl.disabled = value;
  composerInputEl.disabled = value;
  renameCurrentChatBtnEl.disabled = value;
  newChatBtnEl.disabled = value;
  historySearchInputEl.disabled = value;
  promptChipEls.forEach((chip) => {
    chip.disabled = value;
  });
}

function setStatus(message = "", visible = false) {
  statusTextEl.textContent = message || "";
  statusBarEl.classList.toggle("hidden", !visible);
}

function setActivityPhase(value) {
  state.activity.phase = value || "Idle";
  phaseCardEl.textContent = state.activity.phase;
}

function setLastEvent(value) {
  state.activity.lastEvent = value || "Workspace ready";
  lastEventCardEl.textContent = state.activity.lastEvent;
}

function resetTurnActivity() {
  state.activity.toolCount = 0;
  toolCountCardEl.textContent = "0";
  setActivityPhase("Queued");
  setLastEvent("Awaiting tool activity");
}

function incrementToolCount() {
  state.activity.toolCount += 1;
  toolCountCardEl.textContent = String(state.activity.toolCount);
}

function showToast(message, kind = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${kind}`;
  toast.textContent = message;
  toastHostEl.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(8px)";
    setTimeout(() => toast.remove(), 200);
  }, 2600);
}

function downloadFile(filename, content, mimeType = "text/plain;charset=utf-8") {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function buildFollowups(prompt = "", response = "") {
  const focus = (prompt || "").toLowerCase();
  const text = `${prompt}\n${response}`.toLowerCase();
  const picks = [];
  const push = (value) => {
    if (value && !picks.includes(value) && picks.length < 6) picks.push(value);
  };
  if (text.includes("cve")) push("Can you break this down by CVE severity and affected products?");
  if (text.includes("threat actor")) push("Which threat actors showed the largest increase over the same period?");
  if (text.includes("malware")) push("Can you map the malware families to infrastructure and sectors?");
  if (text.includes("infrastructure")) push("Which infrastructure indicators appear across multiple campaigns?");
  if (text.includes("timeline") || text.includes("trend")) push("Show this as a timeline with notable spikes and likely drivers.");
  if (focus.includes("last") || focus.includes("days") || focus.includes("month")) {
    push("Compare this with the previous equivalent time window.");
  }
  push("What evidence rows most strongly support this conclusion?");
  push("Can you validate this with an ES|QL query and show the exact query used?");
  push("What gaps or uncertainty should we account for before acting on this?");
  return picks.slice(0, 6);
}

function sanitizeSuggestionText(value = "") {
  return String(value || "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/(^|\W)\*([^*]+)\*(?=\W|$)/g, "$1$2")
    .replace(/(^|\W)_([^_]+)_(?=\W|$)/g, "$1$2")
    .replace(/^[-*•\d.)\s]+/, "")
    .replace(/,\s*or\s*$/i, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 110);
}

function extractAnswerSuggestions(content = "") {
  const text = String(content || "");
  const picks = [];
  const push = (value) => {
    const cleaned = sanitizeSuggestionText(value);
    if (cleaned && cleaned.length > 6 && !picks.includes(cleaned)) picks.push(cleaned.slice(0, 110));
  };

  const markerMatch = text.match(/if you want[^:\n]*:\s*([\s\S]{0,520})/i);
  if (markerMatch?.[1]) {
    markerMatch[1]
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .slice(0, 8)
      .forEach(push);
  }

  text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => /^[-*•]\s+/.test(line) || /^\d+[.)]\s+/.test(line))
    .slice(0, 8)
    .forEach(push);

  return picks.slice(0, 6);
}

function derivePlan(meta = {}) {
  const tools = Array.isArray(meta.tools_used) ? meta.tools_used : [];
  const steps = tools.map((tool, idx) => `${idx + 1}. ${tool.replaceAll("_", " ")}`);
  return {
    intent: "Investigate user question against RBTN DB with read-only Elasticsearch tools.",
    stages: ["Interpret request", "Validate schema/fields", "Execute queries", "Synthesize evidence-backed answer"],
    tools,
    steps,
  };
}

function setRightPaneMode(mode = "console") {
  state.rightPaneMode = mode;
  const pairs = [
    [consoleTabBtnEl, consolePaneEl, "console"],
    [inspectorTabBtnEl, inspectorPaneEl, "inspector"],
  ];
  pairs.forEach(([tab, pane, key]) => {
    const active = key === mode;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
    pane.classList.toggle("hidden", !active);
  });
}

function normalizeLimitations(meta = {}, toolTrace = []) {
  const flags = [];
  const combined = JSON.stringify(meta || {}).toLowerCase() + JSON.stringify(toolTrace || []).toLowerCase();
  const add = (id, label, tip) => {
    if (!flags.find((item) => item.id === id)) flags.push({ id, label, tip });
  };
  if (combined.includes("sample")) add("sampled", "Sampled", "Result set appears sampled; not all matching records may be represented.");
  if (combined.includes("truncat") || combined.includes("limit")) add("truncated", "Truncated", "Result may be clipped by size or LIMIT settings.");
  if (combined.includes("partial")) add("partial", "Partial", "Only part of the expected result set was returned.");
  if (combined.includes("conflict") || combined.includes("unmapped") || combined.includes("type")) {
    add("schema", "Schema conflict", "Cross-index field mapping/type differences may have affected query behavior.");
  }
  return flags;
}

function updateInspector(meta = {}) {
  const trace = Array.isArray(meta.tool_trace) ? meta.tool_trace : [];
  const queryEntry = [...trace].reverse().find((item) => ["run_esql_query", "run_dsl_query", "validate_dsl_query"].includes(item.tool_name));
  const queryText = queryEntry?.arguments?.query
    || (queryEntry?.arguments?.query_body ? JSON.stringify(queryEntry.arguments.query_body, null, 2) : "");
  inspectorCountPillEl.textContent = trace.length ? `${trace.length} tool event${trace.length === 1 ? "" : "s"}` : "No query yet";
  inspectorQueryEl.textContent = queryText || "Waiting for an Elasticsearch query...";
  inspectorToolsEl.innerHTML = trace.length
    ? trace.map((item) => `<div class="inspector-tool-row"><span>${safeEscape(item.tool_name || "tool")}</span><span data-tooltip="${safeEscape(item.summary || "No summary")}">${safeEscape(item.summary || "No summary")}</span></div>`).join("")
    : `<div class="chat-history-empty">No tool trace for this response.</div>`;
  const flags = normalizeLimitations(meta, trace);
  inspectorFlagsEl.innerHTML = flags.map((flag) => `<span class="result-flag" data-tooltip="${safeEscape(flag.tip)}">${safeEscape(flag.label)}</span>`).join("");
}

function getTooltipAnchor(target) {
  if (!(target instanceof Element)) return null;
  const anchor = target.closest("[data-tooltip]");
  if (!anchor || !anchor.dataset.tooltip || anchor.disabled) return null;
  return anchor;
}

function positionTooltip(anchor) {
  if (!anchor || tooltipEl.classList.contains("hidden")) return;
  const rect = anchor.getBoundingClientRect();
  const tipRect = tooltipEl.getBoundingClientRect();
  const gap = 12;
  let top = rect.top - tipRect.height - gap;
  if (top < 8) top = rect.bottom + gap;
  let left = rect.left + (rect.width - tipRect.width) / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - tipRect.width - 8));
  tooltipEl.style.top = `${top}px`;
  tooltipEl.style.left = `${left}px`;
}

function showTooltip(anchor) {
  if (!anchor) return;
  state.activeTooltipAnchor = anchor;
  tooltipEl.textContent = anchor.dataset.tooltip || "";
  tooltipEl.classList.remove("hidden");
  positionTooltip(anchor);
}

function hideTooltip() {
  state.activeTooltipAnchor = null;
  tooltipEl.classList.add("hidden");
}

function installTooltipSystem() {
  document.addEventListener("mouseover", (event) => {
    const anchor = getTooltipAnchor(event.target);
    if (!anchor || anchor === state.activeTooltipAnchor) return;
    showTooltip(anchor);
  });

  document.addEventListener("mouseout", (event) => {
    if (!state.activeTooltipAnchor) return;
    const fromAnchor = getTooltipAnchor(event.target);
    const toAnchor = getTooltipAnchor(event.relatedTarget);
    if (fromAnchor && fromAnchor === state.activeTooltipAnchor && toAnchor !== state.activeTooltipAnchor) {
      hideTooltip();
    }
  });

  document.addEventListener("focusin", (event) => {
    const anchor = getTooltipAnchor(event.target);
    if (anchor) showTooltip(anchor);
  });

  document.addEventListener("focusout", hideTooltip);
  window.addEventListener("scroll", () => {
    if (state.activeTooltipAnchor) positionTooltip(state.activeTooltipAnchor);
  }, true);
  window.addEventListener("resize", () => {
    if (state.activeTooltipAnchor) positionTooltip(state.activeTooltipAnchor);
  });
}

function openModal({
  title,
  body,
  mode = "confirm",
  confirmText = "Confirm",
  cancelText = "Cancel",
  danger = false,
  initialValue = "",
  placeholder = "",
}) {
  hideTooltip();
  modalTitleEl.textContent = title || "Action required";
  modalBodyEl.innerHTML = body ? `<p>${safeEscape(body)}</p>` : "";
  modalInputWrapEl.classList.toggle("hidden", mode !== "prompt");
  modalInputEl.value = initialValue || "";
  modalInputEl.placeholder = placeholder || "";
  modalConfirmBtnEl.textContent = confirmText;
  modalCancelBtnEl.textContent = cancelText;
  modalConfirmBtnEl.classList.toggle("danger", !!danger);
  state.modalMode = mode;
  modalRootEl.classList.remove("hidden");
  modalRootEl.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";

  return new Promise((resolve) => {
    state.modalResolver = resolve;
    requestAnimationFrame(() => {
      if (mode === "prompt") {
        modalInputEl.focus();
        modalInputEl.select();
      } else {
        modalConfirmBtnEl.focus();
      }
    });
  });
}

function closeModal(result) {
  if (!state.modalResolver) return;
  const resolver = state.modalResolver;
  state.modalResolver = null;
  state.modalMode = null;
  modalRootEl.classList.add("hidden");
  modalRootEl.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
  resolver(result);
  composerInputEl.focus();
}

function installModalSystem() {
  modalCancelBtnEl.addEventListener("click", () => closeModal({ confirmed: false }));
  modalCloseBtnEl.addEventListener("click", () => closeModal({ confirmed: false }));
  modalConfirmBtnEl.addEventListener("click", () => {
    const payload = { confirmed: true };
    if (state.modalMode === "prompt") payload.value = modalInputEl.value;
    closeModal(payload);
  });
  modalRootEl.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.dataset.closeModal) {
      closeModal({ confirmed: false });
    }
  });
  modalInputEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      modalConfirmBtnEl.click();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (modalRootEl.classList.contains("hidden")) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeModal({ confirmed: false });
    }
  });
}

function formatInlineMarkdown(text) {
  let html = safeEscape(text || "");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  html = html.replace(/(^|\W)\*([^*]+)\*(?=\W|$)/g, "$1<em>$2</em>");
  html = html.replace(/(^|\W)_([^_]+)_(?=\W|$)/g, "$1<em>$2</em>");
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  html = html.replace(/(^|\s)(https?:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>');
  return html;
}

function tryRenderTable(lines, startIndex) {
  const headerLine = lines[startIndex];
  const dividerLine = lines[startIndex + 1];
  if (!headerLine || !dividerLine) return null;
  if (!headerLine.includes("|") || !/^\s*\|?\s*[-:]+[-| :]*\|?\s*$/.test(dividerLine)) return null;

  const parseCells = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
  const headers = parseCells(headerLine);
  const rows = [];
  let idx = startIndex + 2;
  while (idx < lines.length && lines[idx].includes("|")) {
    const cells = parseCells(lines[idx]);
    if (!cells.length || cells.every((cell) => !cell)) break;
    rows.push(cells);
    idx += 1;
  }

  const headHtml = headers.map((cell) => `<th>${formatInlineMarkdown(cell)}</th>`).join("");
  const bodyHtml = rows.map((row) => `<tr>${row.map((cell) => `<td>${formatInlineMarkdown(cell)}</td>`).join("")}</tr>`).join("");
  return {
    html: `<table><thead><tr>${headHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`,
    nextIndex: idx,
  };
}

function renderMarkdown(content = "") {
  const text = String(content || "").replace(/\r\n/g, "\n");
  const lines = text.split("\n");
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }

    const table = tryRenderTable(lines, i);
    if (table) {
      blocks.push(table.html);
      i = table.nextIndex;
      continue;
    }

    if (line.trim().startsWith("```") || line.trim().startsWith("~~~")) {
      const fence = line.trim().slice(0, 3);
      const codeLines = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith(fence)) {
        codeLines.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      blocks.push(`<pre><code>${safeEscape(codeLines.join("\n"))}</code></pre>`);
      continue;
    }

    if (/^\s*#{1,4}\s+/.test(line)) {
      const level = Math.min(4, line.match(/^\s*(#+)/)[1].length);
      const textOnly = line.replace(/^\s*#{1,4}\s+/, "");
      blocks.push(`<h${level}>${formatInlineMarkdown(textOnly)}</h${level}>`);
      i += 1;
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      const quoteLines = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        quoteLines.push(lines[i].replace(/^\s*>\s?/, ""));
        i += 1;
      }
      blocks.push(`<blockquote>${quoteLines.map((part) => `<p>${formatInlineMarkdown(part)}</p>`).join("")}</blockquote>`);
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i += 1;
      }
      blocks.push(`<ul>${items.map((item) => `<li>${formatInlineMarkdown(item)}</li>`).join("")}</ul>`);
      continue;
    }

    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+[.)]\s+/, ""));
        i += 1;
      }
      blocks.push(`<ol>${items.map((item) => `<li>${formatInlineMarkdown(item)}</li>`).join("")}</ol>`);
      continue;
    }

    if (/^\s*---+\s*$/.test(line) || /^\s*\*\*\*+\s*$/.test(line)) {
      blocks.push("<hr>");
      i += 1;
      continue;
    }

    const paragraphLines = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^\s*[-*]\s+/.test(lines[i]) &&
      !/^\s*\d+[.)]\s+/.test(lines[i]) &&
      !/^\s*>\s?/.test(lines[i]) &&
      !/^\s*#{1,4}\s+/.test(lines[i]) &&
      !lines[i].trim().startsWith("```") &&
      !lines[i].trim().startsWith("~~~") &&
      !/^\s*---+\s*$/.test(lines[i]) &&
      !/^\s*\*\*\*+\s*$/.test(lines[i])
    ) {
      paragraphLines.push(lines[i]);
      i += 1;
    }
    const paragraphHtml = formatInlineMarkdown(paragraphLines.join("\n")).replace(/\n/g, "<br>");
    blocks.push(`<p>${paragraphHtml}</p>`);
  }

  return blocks.join("");
}

function terminalLine(text, kind = "info", eventType = null) {
  const entry = document.createElement("div");
  entry.className = `terminal-entry ${kind}`;
  entry.innerHTML = `
    <div class="terminal-meta">
      <span class="terminal-time">${safeEscape(new Date().toLocaleTimeString())}</span>
      <span class="terminal-kind">${safeEscape(kind)}</span>
      ${eventType ? `<span class="terminal-kind">${safeEscape(eventType)}</span>` : ""}
    </div>
    <div class="terminal-body">${safeEscape(text)}</div>
  `;
  terminalOutputEl.appendChild(entry);
  requestAnimationFrame(() => {
    scrollTerminalToBottom(true);
  });
}

function clearTerminal() {
  terminalOutputEl.innerHTML = "";
  setLastEvent("Execution console cleared");
  showToast("Execution console cleared", "info");
}

function groupChatsByDay(chats) {
  const groups = new Map();
  chats.forEach((chat) => {
    const stamp = chat.updated_at || chat.created_at;
    const key = fmtDayKey(stamp);
    if (!groups.has(key)) {
      groups.set(key, { key, label: fmtDayLabel(stamp), items: [] });
    }
    groups.get(key).items.push(chat);
  });
  return Array.from(groups.values());
}

function getFilteredChats() {
  const query = state.historyFilter.trim().toLowerCase();
  if (!query) return [...state.chats];
  return state.chats.filter((chat) => {
    const title = (chat.title || "").toLowerCase();
    return title.includes(query);
  });
}

function renderChats() {
  const chats = getFilteredChats();
  chatListEl.innerHTML = "";
  historyCountPillEl.textContent = `${chats.length} ${chats.length === 1 ? "chat" : "chats"}`;

  if (!chats.length) {
    const empty = document.createElement("div");
    empty.className = "chat-history-empty";
    empty.textContent = state.historyFilter ? "No chats match this search" : "No chats yet";
    chatListEl.appendChild(empty);
    return;
  }

  const groups = groupChatsByDay(chats);
  const visibleChats = Math.min(chats.length, 10);
  const estimatedHeight = visibleChats * 84 + groups.length * 34 + 20;
  chatListEl.parentElement.style.setProperty("--history-max-visible", `${estimatedHeight}px`);

  groups.forEach((group) => {
    const section = document.createElement("section");
    section.className = "chat-group";

    const label = document.createElement("div");
    label.className = "chat-group-label";
    label.textContent = group.label;
    section.appendChild(label);

    const list = document.createElement("div");
    list.className = "chat-group-items";

    group.items.forEach((chat) => {
      const shell = document.createElement("div");
      shell.className = `chat-item ${chat.id === state.currentChatId ? "active" : ""}`;

      const mainBtn = document.createElement("button");
      mainBtn.type = "button";
      mainBtn.className = "chat-item-main";
      mainBtn.dataset.tooltip = chat.title || "New chat";
      mainBtn.innerHTML = `
        <div class="chat-item-title">${safeEscape(chat.title || "New chat")}</div>
        <div class="chat-item-time-row">
          <span>${safeEscape(fmtTime(chat.updated_at || chat.created_at || ""))}</span>
          <span>•</span>
          <span>${safeEscape(fmtRelativeShort(chat.updated_at || chat.created_at || ""))}</span>
        </div>
      `;
      mainBtn.addEventListener("click", () => switchChat(chat.id));

      const actions = document.createElement("div");
      actions.className = "chat-item-actions";

      const renameBtn = document.createElement("button");
      renameBtn.type = "button";
      renameBtn.className = "chat-action-btn icon-only";
      renameBtn.textContent = "✎";
      renameBtn.setAttribute("aria-label", `Rename ${chat.title || "New chat"}`);
      renameBtn.dataset.tooltip = `Rename “${chat.title || "New chat"}”`;
      renameBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        renameChat(chat.id, chat.title || "New chat");
      });

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "chat-action-btn danger icon-only";
      deleteBtn.textContent = "🗑";
      deleteBtn.setAttribute("aria-label", `Delete ${chat.title || "New chat"}`);
      deleteBtn.dataset.tooltip = `Delete “${chat.title || "New chat"}”`;
      deleteBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        deleteChat(chat.id, chat.title || "New chat");
      });

      actions.append(renameBtn, deleteBtn);
      shell.append(mainBtn, actions);
      list.appendChild(shell);
    });

    section.appendChild(list);
    chatListEl.appendChild(section);
  });
}

function showEmptyState() {
  chatWindowEl.innerHTML = `
    <section class="empty-state">
      <h3>Run investigations in plain language.</h3>
      <p>LidarKinesis IntelChat lets you explore RBTN DB like a professional analyst workspace: a clean conversation rail in the center, durable history on the left, and live execution telemetry on the right.</p>
      <div class="empty-grid">
        <div class="empty-panel">
          <div class="empty-panel-title">Schema-aware exploration</div>
          <div class="empty-panel-copy">“Which fields mention malware families in the last 14 days?”</div>
        </div>
        <div class="empty-panel">
          <div class="empty-panel-title">Top-N investigations</div>
          <div class="empty-panel-copy">“List the top 5 threat actors this month and show the evidence.”</div>
        </div>
        <div class="empty-panel">
          <div class="empty-panel-title">Readable answers</div>
          <div class="empty-panel-copy">Responses render with headings, bullets, tables, code blocks, and links instead of raw dumps.</div>
        </div>
        <div class="empty-panel">
          <div class="empty-panel-title">Visible tool execution</div>
          <div class="empty-panel-copy">The execution console streams tools, script paths, arguments, results, and errors without breaking the chat flow.</div>
        </div>
      </div>
    </section>
  `;
}

function applyMessageContent(bubble, content, role, streaming = false) {
  bubble.classList.toggle("is-streaming", streaming && role === "assistant");
  if (role === "assistant") {
    bubble.innerHTML = renderMarkdown(content || "");
  } else {
    bubble.innerHTML = `<p>${formatInlineMarkdown(content || "")}</p>`;
  }
}

function handleCopyMessage(node, content) {
  const btn = node.querySelector(".message-copy");
  if (!btn) return;
  btn.dataset.tooltip = "Copy message";
  btn.addEventListener("click", async () => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(content || "");
      } else {
        const ta = document.createElement("textarea");
        ta.value = content || "";
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
      }
      showToast("Message copied", "success");
    } catch {
      showToast("Copy failed", "error");
    }
  });
}

function handleExportMessage(node, content, meta = {}) {
  const btn = node.querySelector(".message-export");
  if (!btn) return;
  btn.dataset.tooltip = "Export this response as Markdown";
  btn.classList.toggle("hidden", node.classList.contains("user"));
  btn.addEventListener("click", () => {
    const title = (chatTitleEl.textContent || "chat-result").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const filename = `${title || "chat-result"}-${stamp}.md`;
    const body = `# ${chatTitleEl.textContent || "Chat result"}\n\n${content || ""}\n\n---\n\n\`\`\`json\n${JSON.stringify(meta || {}, null, 2)}\n\`\`\`\n`;
    downloadFile(filename, body, "text/markdown;charset=utf-8");
    showToast(`Exported ${filename}`, "success");
  });
}

function decorateAssistantBubble(node, content = "", meta = {}) {
  const bubble = node.querySelector(".message-bubble");
  const existing = bubble.querySelector(".message-tools");
  if (existing) existing.remove();
  if (meta.tools_used?.length) {
    const wrap = document.createElement("div");
    wrap.className = "message-tools";
    meta.tools_used.forEach((tool) => {
      const chip = document.createElement("span");
      chip.className = "tool-chip";
      chip.textContent = tool;
      wrap.appendChild(chip);
    });
    bubble.appendChild(wrap);
  }

  const flags = normalizeLimitations(meta, meta.tool_trace || []);
  const existingFlags = bubble.querySelector(".message-flags");
  if (existingFlags) existingFlags.remove();
  if (flags.length) {
    const flagWrap = document.createElement("div");
    flagWrap.className = "message-flags";
    flags.forEach((flag) => {
      const chip = document.createElement("span");
      chip.className = "result-flag";
      chip.dataset.tooltip = flag.tip;
      chip.textContent = flag.label;
      flagWrap.appendChild(chip);
    });
    bubble.appendChild(flagWrap);
  }

  const followupsWrap = node.querySelector(".message-followups");
  followupsWrap.innerHTML = "";
  const modelFollowups = Array.isArray(meta.followups)
    ? meta.followups
      .map((item) => sanitizeSuggestionText(String(item || "")))
      .filter(Boolean)
    : [];
  const answerFollowups = extractAnswerSuggestions(content);
  const followups = modelFollowups.length
    ? modelFollowups.slice(0, 6)
    : answerFollowups;
  if (followups.length) {
    followupsWrap.classList.remove("hidden");
    const label = document.createElement("div");
    label.className = "followup-label";
    label.textContent = "Suggested follow-ups";
    followupsWrap.appendChild(label);
    followups.forEach((entry) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "followup-chip";
      btn.textContent = entry;
      btn.dataset.tooltip = "Click to send this as your next prompt";
      btn.addEventListener("click", () => {
        composerInputEl.value = entry;
        autoGrowTextarea();
        composerInputEl.focus();
      });
      followupsWrap.appendChild(btn);
    });
  } else {
    followupsWrap.classList.add("hidden");
  }

  const oldPlan = bubble.querySelector(".agent-plan");
  if (oldPlan) oldPlan.remove();
  const plan = derivePlan(meta);
  const planNode = document.createElement("details");
  planNode.className = "agent-plan";
  planNode.open = !!state.planMode;
  planNode.innerHTML = `
    <summary data-tooltip="Compact execution plan view: intent, stages, and tools used">Agent plan</summary>
    <div class="agent-plan-body">
      <div><strong>Intent:</strong> ${safeEscape(plan.intent)}</div>
      <div><strong>Stages:</strong> ${safeEscape(plan.stages.join(" → "))}</div>
      <div><strong>Tools:</strong> ${safeEscape(plan.tools.join(", ") || "None")}</div>
      <div><strong>Steps:</strong> ${safeEscape(plan.steps.join(" | ") || "No explicit tool steps")}</div>
    </div>
  `;
  bubble.appendChild(planNode);
}

function createMessageElement(role, content, meta = {}) {
  const node = messageTemplate.content.firstElementChild.cloneNode(true);
  node.classList.add(role);
  node.querySelector(".message-role").textContent = role === "user" ? "You" : "LidarKinesis IntelChat";
  node.querySelector(".message-avatar").textContent = role === "user" ? "Y" : "LK";
  node.querySelector(".message-meta").textContent = meta.created_at ? fmtDate(meta.created_at) : "";
  const bubble = node.querySelector(".message-bubble");
  applyMessageContent(bubble, content, role, false);
  handleCopyMessage(node, content);
  handleExportMessage(node, content, meta);
  if (role === "assistant") decorateAssistantBubble(node, content, meta);
  return node;
}

function appendMessage(role, content, meta = {}) {
  const node = createMessageElement(role, content, meta);
  chatWindowEl.appendChild(node);
  scrollChatToBottom(true);
  return node;
}

function replacePendingAssistant(content, meta = {}) {
  if (!state.pendingAssistantElement) {
    appendMessage("assistant", content, meta);
    return;
  }
  const bubble = state.pendingAssistantElement.querySelector(".message-bubble");
  applyMessageContent(bubble, content, "assistant", false);
  const metaEl = state.pendingAssistantElement.querySelector(".message-meta");
  metaEl.textContent = meta.created_at ? fmtDate(meta.created_at) : "";
  const newCopy = state.pendingAssistantElement.querySelector(".message-copy").cloneNode(true);
  state.pendingAssistantElement.querySelector(".message-copy").replaceWith(newCopy);
  const newExport = state.pendingAssistantElement.querySelector(".message-export").cloneNode(true);
  state.pendingAssistantElement.querySelector(".message-export").replaceWith(newExport);
  handleCopyMessage(state.pendingAssistantElement, content);
  handleExportMessage(state.pendingAssistantElement, content, meta);
  decorateAssistantBubble(state.pendingAssistantElement, content, meta);
  updateInspector(meta);
  state.pendingAssistantElement = null;
  scrollChatToBottom(true);
}

function appendPendingAssistant() {
  state.pendingAssistantElement = appendMessage("assistant", "Working on it…", { created_at: new Date().toISOString() });
  const bubble = state.pendingAssistantElement.querySelector(".message-bubble");
  applyMessageContent(bubble, "Working on it…", "assistant", true);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await res.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      if (!res.ok) throw new Error(`Request failed (${res.status}): ${text.slice(0, 180)}`);
      throw new Error(`Unexpected server response (${res.status})`);
    }
  }
  if (!res.ok) throw new Error(data.error || data.message || `HTTP ${res.status}`);
  return data;
}

async function loadHealth() {
  try {
    const data = await api("/api/health");
    const indexChip = document.getElementById("lastEventCard");
    if (indexChip && data.default_index) {
      indexChip.dataset.tooltip = `Current default index: ${data.default_index}`;
    }
    setLastEvent("Workspace ready");
  } catch (err) {
    terminalLine(`Health check failed: ${err.message}`, "error", "health");
    showToast("Workspace health check failed", "error");
  }
}

async function refreshChats() {
  const data = await api("/api/chats");
  state.chats = data.items || [];
  renderChats();
}

async function loadChats() {
  await refreshChats();
  if (!state.currentChatId) {
    if (!state.chats.length) {
      await createNewChat();
    } else {
      await switchChat(state.chats[0].id);
    }
  }
}

async function createNewChat() {
  const chat = await api("/api/chats", {
    method: "POST",
    body: JSON.stringify({ title: "New chat" }),
  });
  state.chats.unshift(chat);
  state.currentChatId = chat.id;
  renderChats();
  chatTitleEl.textContent = chat.title;
  state.pendingAssistantElement = null;
  setStatus("", false);
  setActivityPhase("Idle");
  setLastEvent("Fresh investigation thread created");
  showEmptyState();
  connectSocket(chat.id);
  showToast("New chat created", "success");
}

async function switchChat(chatId) {
  state.currentChatId = chatId;
  state.pendingAssistantElement = null;
  renderChats();
  const data = await api(`/api/chats/${chatId}/messages`);
  chatTitleEl.textContent = data.chat.title || "New chat";
  chatWindowEl.innerHTML = "";
  if (!data.items.length) {
    showEmptyState();
    updateInspector({});
  } else {
    data.items.forEach((message) => appendMessage(message.role, message.content, message.meta || message));
    const latestAssistant = [...data.items].reverse().find((message) => message.role === "assistant");
    updateInspector(latestAssistant?.meta || {});
  }
  setActivityPhase("Idle");
  connectSocket(chatId);
}

function clearSocketReconnectTimer() {
  if (state.wsReconnectTimer) {
    clearTimeout(state.wsReconnectTimer);
    state.wsReconnectTimer = null;
  }
}

function clearSocketHeartbeat() {
  if (state.wsHeartbeatTimer) {
    clearInterval(state.wsHeartbeatTimer);
    state.wsHeartbeatTimer = null;
  }
}

function startSocketHeartbeat() {
  clearSocketHeartbeat();
  state.wsLastPongAt = Date.now();
  state.wsHeartbeatTimer = setInterval(() => {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
    try {
      state.ws.send(JSON.stringify({ type: "ping" }));
    } catch {
      terminalLine("Heartbeat send failed", "error", "socket");
    }
  }, 25000);
}

function scheduleSocketReconnect(chatId, reason = "Connection lost") {
  if (!chatId || state.wsManualClose || state.currentChatId !== chatId) return;
  clearSocketReconnectTimer();
  const attempt = Math.min(state.wsReconnectAttempts + 1, 6);
  state.wsReconnectAttempts = attempt;
  const delay = Math.min(1000 * (2 ** (attempt - 1)), 12000);
  setStatus(`${reason}. Reconnecting…`, true);
  setActivityPhase("Reconnecting");
  setLastEvent(`Socket reconnect scheduled (${delay} ms)`);
  state.wsReconnectTimer = setTimeout(() => {
    connectSocket(chatId, { preserveQueue: true, reconnecting: true });
  }, delay);
}

function flushPendingOutbound() {
  if (!state.pendingOutbound || !state.ws || state.ws.readyState !== WebSocket.OPEN) return;
  const payload = state.pendingOutbound;
  if (payload.chatId !== state.currentChatId) {
    state.pendingOutbound = null;
    return;
  }
  state.pendingOutbound = null;
  try {
    state.ws.send(JSON.stringify(payload.message));
    setStatus("Thinking…", true);
    setActivityPhase("Queued");
    setLastEvent("Queued message sent after reconnect");
    terminalLine(`USER
${payload.message.content}`, "info", "user");
  } catch {
    state.pendingOutbound = payload;
    scheduleSocketReconnect(payload.chatId, "Send failed");
  }
}

function closeSocket({ manual = true } = {}) {
  state.wsManualClose = manual;
  clearSocketReconnectTimer();
  clearSocketHeartbeat();
  if (state.ws) {
    try {
      state.ws.close();
    } catch {
      // ignore close race
    }
    state.ws = null;
  }
}

function connectSocket(chatId, { preserveQueue = false, reconnecting = false } = {}) {
  if (!chatId) return;
  if (!preserveQueue) state.pendingOutbound = null;
  closeSocket({ manual: true });
  state.wsManualClose = false;
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${protocol}://${window.location.host}/ws/chat/${chatId}`;
  const generation = state.wsGeneration + 1;
  state.wsGeneration = generation;
  const ws = new WebSocket(wsUrl);
  state.ws = ws;

  ws.addEventListener("open", () => {
    if (state.wsGeneration !== generation) return;
    clearSocketReconnectTimer();
    state.wsReconnectAttempts = 0;
    startSocketHeartbeat();
    terminalLine(`${reconnecting ? "Reconnected" : "Connected"} to chat ${chatId}`, "success", "socket");
    setStatus("", false);
    setActivityPhase(state.busy ? "Working" : "Idle");
    setLastEvent(reconnecting ? "Socket reconnected" : "Socket connected");
    flushPendingOutbound();
  });

  ws.addEventListener("message", (event) => {
    if (state.wsGeneration !== generation) return;
    try {
      handleSocketEvent(JSON.parse(event.data));
    } catch {
      terminalLine("Received malformed websocket payload", "error", "socket");
    }
  });

  ws.addEventListener("close", () => {
    if (state.wsGeneration !== generation) return;
    clearSocketHeartbeat();
    state.ws = null;
    terminalLine("WebSocket closed", reconnecting || state.busy || state.pendingOutbound ? "error" : "info", "socket");
    if (state.wsManualClose || state.currentChatId !== chatId) return;
    if (state.busy || state.pendingOutbound) {
      setStatus("Connection lost. Reconnecting…", true);
      setActivityPhase("Degraded");
      setLastEvent("Connection closed during a turn");
    }
    scheduleSocketReconnect(chatId, "Connection lost");
  });

  ws.addEventListener("error", () => {
    if (state.wsGeneration !== generation) return;
    terminalLine("WebSocket error", "error", "socket");
    setLastEvent("WebSocket error");
  });
}

function updateChatTitleLocally(chatId, title) {
  const target = state.chats.find((chat) => chat.id === chatId);
  if (target) target.title = title;
  if (state.currentChatId === chatId) chatTitleEl.textContent = title;
  renderChats();
}

function handleSocketEvent(payload) {
  const type = payload.type;
  switch (type) {
    case "message_saved":
      setLastEvent("Message persisted");
      break;
    case "chat_title":
      updateChatTitleLocally(payload.chat_id, payload.title);
      setLastEvent("Chat title updated");
      break;
    case "status":
      setStatus(payload.message, true);
      setActivityPhase(payload.phase || "Working");
      setLastEvent(payload.message || "Status update");
      terminalLine(`${payload.phase || "status"} :: ${payload.message}`, "info", "status");
      break;
    case "tool_start":
      state.pendingToolEvents.push({
        when: new Date().toISOString(),
        tool_name: payload.tool_name,
        arguments: payload.arguments || {},
        summary: "started",
      });
      incrementToolCount();
      setActivityPhase("Tool execution");
      setLastEvent(`${payload.tool_name} started`);
      terminalLine(
        `SKILL ${payload.skill_name}\nTOOL ${payload.tool_name}\nSCRIPT ${payload.script_path}\nARGS ${JSON.stringify(payload.arguments, null, 2)}`,
        "info",
        "tool_start",
      );
      break;
    case "tool_result":
      state.pendingToolEvents.push({
        when: new Date().toISOString(),
        tool_name: payload.tool_name,
        summary: payload.summary || "completed",
      });
      setLastEvent(`${payload.tool_name} completed`);
      terminalLine(`DONE ${payload.tool_name}\n${payload.summary}\n${payload.result_preview}`, "success", "tool_result");
      break;
    case "tool_error":
      setActivityPhase("Tool error");
      setLastEvent(`${payload.tool_name} failed`);
      terminalLine(`ERROR ${payload.tool_name}\n${payload.stderr || payload.stdout || "unknown"}`, "error", "tool_error");
      break;
    case "assistant_final":
      state.pendingToolEvents = [];
      replacePendingAssistant(payload.content, payload.meta || {});
      setStatus("", false);
      setBusy(false);
      setActivityPhase("Complete");
      setLastEvent("Assistant answer ready");
      refreshChats();
      composerInputEl.focus();
      break;
    case "error":
      terminalLine(payload.message || "Unknown error", "error", "error");
      setStatus("", false);
      setBusy(false);
      setActivityPhase("Error");
      setLastEvent(payload.message || "Unknown error");
      replacePendingAssistant(`Error: ${payload.message || "Unknown error"}`);
      showToast(payload.message || "Unknown error", "error");
      break;
    case "pong":
      state.wsLastPongAt = Date.now();
      break;
    default:
      terminalLine(`EVENT ${type}\n${JSON.stringify(payload, null, 2)}`, "info", type);
  }
}

async function promptForChatTitle(currentTitle) {
  const result = await openModal({
    title: "Rename chat",
    body: "Give this conversation a clear, memorable title so it is easier to find later.",
    mode: "prompt",
    confirmText: "Save title",
    cancelText: "Cancel",
    initialValue: currentTitle || "New chat",
    placeholder: "Threat actor trends — Q3 review",
  });
  if (!result?.confirmed) return null;
  const cleaned = String(result.value || "").trim();
  return cleaned || null;
}

async function renameChat(chatId, currentTitle = "New chat") {
  if (state.busy) return;
  const title = await promptForChatTitle(currentTitle);
  if (!title) return;
  try {
    const updated = await api(`/api/chats/${chatId}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    });
    updateChatTitleLocally(chatId, updated.title || title);
    await refreshChats();
    if (state.currentChatId === chatId) chatTitleEl.textContent = updated.title || title;
    terminalLine(`Renamed chat to: ${updated.title || title}`, "success", "chat");
    setLastEvent("Chat renamed");
    showToast("Chat renamed", "success");
  } catch (err) {
    terminalLine(`Rename failed: ${err.message}`, "error", "chat");
    showToast(`Rename failed: ${err.message}`, "error");
  }
}

async function deleteChat(chatId, currentTitle = "New chat") {
  if (state.busy) return;
  const result = await openModal({
    title: "Delete chat",
    body: `Delete “${currentTitle}”? This cannot be undone and will remove the conversation and its saved messages from the local history.`,
    mode: "confirm",
    confirmText: "Delete chat",
    cancelText: "Keep chat",
    danger: true,
  });
  if (!result?.confirmed) return;

  try {
    await api(`/api/chats/${chatId}`, { method: "DELETE" });
    terminalLine(`Deleted chat: ${currentTitle}`, "success", "chat");
    setLastEvent("Chat deleted");
    showToast("Chat deleted", "success");
    const deletingCurrent = state.currentChatId === chatId;
    state.chats = state.chats.filter((chat) => chat.id !== chatId);
    renderChats();
    if (deletingCurrent) {
      closeSocket();
      state.currentChatId = null;
      if (state.chats.length) {
        await switchChat(state.chats[0].id);
      } else {
        await createNewChat();
      }
    }
  } catch (err) {
    terminalLine(`Delete failed: ${err.message}`, "error", "chat");
    showToast(`Delete failed: ${err.message}`, "error");
  }
}

function sendMessage() {
  const text = composerInputEl.value.trim();
  if (!text || state.busy) return;
  state.lastUserPrompt = text;
  if (chatWindowEl.querySelector(".empty-state")) {
    chatWindowEl.innerHTML = "";
  }
  appendMessage("user", text, { created_at: new Date().toISOString() });
  appendPendingAssistant();
  setBusy(true);
  resetTurnActivity();

  const payload = { chatId: state.currentChatId, message: { type: "user_message", content: text } };
  const socketReady = state.ws && state.ws.readyState === WebSocket.OPEN;
  const socketConnecting = state.ws && state.ws.readyState === WebSocket.CONNECTING;

  if (socketReady) {
    setStatus("Thinking…", true);
    terminalLine(`USER
${text}`, "info", "user");
    state.ws.send(JSON.stringify(payload.message));
  } else {
    state.pendingOutbound = payload;
    setStatus(socketConnecting ? "Connecting…" : "Reconnecting…", true);
    setActivityPhase("Reconnecting");
    setLastEvent(socketConnecting ? "Waiting for socket to open" : "Socket reconnect requested");
    terminalLine(socketConnecting ? "Socket is still connecting. Queued message." : "Socket not ready. Queued message and reconnecting.", "info", "socket");
    if (!socketConnecting) {
      connectSocket(state.currentChatId, { preserveQueue: true, reconnecting: true });
    }
  }

  composerInputEl.value = "";
  autoGrowTextarea();
}

sendBtnEl.addEventListener("click", sendMessage);
newChatBtnEl.addEventListener("click", createNewChat);
renameCurrentChatBtnEl.addEventListener("click", async () => {
  if (!state.currentChatId) return;
  const current = state.chats.find((chat) => chat.id === state.currentChatId);
  await renameChat(state.currentChatId, current?.title || chatTitleEl.textContent || "New chat");
});
toggleTerminalBtnEl.addEventListener("click", () => {
  state.terminalVisible = !state.terminalVisible;
  shellEl.classList.toggle("console-hidden", !state.terminalVisible);
  toggleTerminalBtnEl.textContent = state.terminalVisible ? "Hide console" : "Show console";
  toggleTerminalBtnEl.dataset.tooltip = state.terminalVisible ? "Show or hide the execution console" : "Show the execution console";
});
consoleTabBtnEl.addEventListener("click", () => setRightPaneMode("console"));
inspectorTabBtnEl.addEventListener("click", () => setRightPaneMode("inspector"));
clearTerminalBtnEl.addEventListener("click", clearTerminal);
composerInputEl.addEventListener("input", autoGrowTextarea);
composerInputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});
historySearchInputEl.addEventListener("input", (event) => {
  state.historyFilter = event.target.value || "";
  renderChats();
});
promptChipEls.forEach((chip) => {
  chip.addEventListener("click", () => {
    if (state.busy) return;
    composerInputEl.value = chip.dataset.prompt || "";
    autoGrowTextarea();
    composerInputEl.focus();
  });
});

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    historySearchInputEl.focus();
    historySearchInputEl.select();
  }
});

window.addEventListener("beforeunload", () => closeSocket({ manual: true }));
window.addEventListener("load", async () => {
  installTooltipSystem();
  installModalSystem();
  autoGrowTextarea();
  setRightPaneMode("console");
  await loadHealth();
  await loadChats();
  composerInputEl.focus();
});
