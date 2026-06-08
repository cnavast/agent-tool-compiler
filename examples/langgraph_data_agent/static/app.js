const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const messages = document.querySelector("#messages");
const chatHistory = [];

function addMessage(role, text) {
  const node = document.createElement("article");
  node.className = `message ${role}`;
  node.innerHTML = `<span class="label">${role}</span><div class="content"></div>`;
  node.querySelector(".content").innerHTML = renderMarkdown(text);
  messages.appendChild(node);
  node.scrollIntoView({ behavior: "smooth", block: "end" });
}

function renderMarkdown(text) {
  const lines = escapeHtml(text).split(/\r?\n/);
  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (line.trim().startsWith("```")) {
      const code = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      index += 1;
      blocks.push(`<pre><code>${code.join("\n")}</code></pre>`);
      continue;
    }

    if (isTableStart(lines, index)) {
      const table = [];
      while (index < lines.length && lines[index].includes("|")) {
        table.push(lines[index]);
        index += 1;
      }
      blocks.push(renderTable(table));
      continue;
    }

    if (/^#{1,6}\s+/.test(line)) {
      const level = Math.min(line.match(/^#+/)[0].length, 4);
      const text = line.replace(/^#{1,6}\s+/, "");
      blocks.push(`<h${level}>${inlineMarkdown(text)}</h${level}>`);
      index += 1;
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, ""));
        index += 1;
      }
      blocks.push(`<ul>${items.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</ul>`);
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push(`<ol>${items.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</ol>`);
      continue;
    }

    const paragraph = [line];
    index += 1;
    while (
      index < lines.length &&
      lines[index].trim() &&
      !lines[index].trim().startsWith("```") &&
      !isTableStart(lines, index) &&
      !/^#{1,6}\s+/.test(lines[index]) &&
      !/^\s*[-*]\s+/.test(lines[index]) &&
      !/^\s*\d+\.\s+/.test(lines[index])
    ) {
      paragraph.push(lines[index]);
      index += 1;
    }
    blocks.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
  }

  return blocks.join("");
}

function isTableStart(lines, index) {
  return (
    index + 1 < lines.length &&
    lines[index].includes("|") &&
    isTableSeparator(lines[index + 1])
  );
}

function isTableSeparator(line) {
  const cells = line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function renderTable(lines) {
  const rows = lines
    .filter((line, index) => index !== 1)
    .map((line) =>
      line
        .trim()
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((cell) => cell.trim()),
    );
  const header = rows[0] || [];
  const body = rows.slice(1);
  return `
    <div class="table-wrap">
      <table>
        <thead><tr>${header.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead>
        <tbody>${body
          .map((row) => `<tr>${row.map((cell) => `<td>${inlineMarkdown(cell)}</td>`).join("")}</tr>`)
          .join("")}</tbody>
      </table>
    </div>
  `;
}

function inlineMarkdown(text) {
  return text
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function addCompileCard(atc) {
  const card = document.createElement("article");
  card.className = "compile-card";
  const tools = atc.summary.tool_names.join(", ") || "none";
  card.innerHTML = `
    <strong>Promote this workflow to reusable MCP tool?</strong>
    <div class="metrics">
      <span>Tools used: ${tools}</span>
      <span>Total tokens: ${atc.summary.total_tokens}</span>
      <span>Output tokens: ${atc.summary.output_tokens}</span>
      <span>Final answer tokens: ${atc.summary.final_answer_tokens}</span>
      <span>Work/answer ratio: ${atc.summary.work_to_answer_ratio}</span>
    </div>
    <button type="button">Compile</button>
  `;
  const button = card.querySelector("button");
  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "Compiling...";
    try {
      const response = await fetch("/atc/compile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate: atc.candidate }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || response.statusText);
      }
      button.textContent = `Compiled as ${payload.capability_name}.`;
    } catch (error) {
      button.textContent = `Compile failed: ${error.message}`;
    }
  });
  messages.appendChild(card);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  addMessage("user", message);
  chatHistory.push({ role: "user", content: message });
  input.value = "";
  sendButton.disabled = true;
  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: chatHistory }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || response.statusText);
    }
    const answer = payload.answer || JSON.stringify(payload, null, 2);
    addMessage("assistant", answer);
    chatHistory.push({ role: "assistant", content: answer });
    if (payload.atc?.can_compile) {
      addCompileCard(payload.atc);
    }
  } catch (error) {
    chatHistory.pop();
    addMessage("assistant", `Request failed: ${error}`);
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
});
