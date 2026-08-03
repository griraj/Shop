// ---------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
  });
});

// ---------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------
function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = String(str ?? "");
  return d.innerHTML;
}

function money(n) {
  return "₹" + Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return data;
}

// ---------------------------------------------------------------------
// Items
// ---------------------------------------------------------------------
let categoriesCache = [];

async function loadCategories() {
  categoriesCache = await api("/api/categories");
  const body = document.getElementById("categoriesBody");
  body.innerHTML = categoriesCache.length
    ? categoriesCache.map(c => `
        <tr>
          <td>${c.categoryid}</td>
          <td>${escapeHtml(c.categoryname)}</td>
          <td class="num">${c.item_count}</td>
        </tr>`).join("")
    : `<tr><td colspan="3" class="loading-row">No categories yet.</td></tr>`;

  const select = document.getElementById("newItemCategory");
  select.innerHTML = categoriesCache.map(c => `<option value="${c.categoryid}">${escapeHtml(c.categoryname)}</option>`).join("");
}

async function loadItems() {
  const items = await api("/api/items");
  const body = document.getElementById("itemsBody");
  body.innerHTML = items.length
    ? items.map(i => `
        <tr data-id="${i.itemid}">
          <td>${i.itemid}</td>
          <td>${escapeHtml(i.itemname)}</td>
          <td>${escapeHtml(i.categoryname || "—")}</td>
          <td class="num">${money(i.price)}</td>
          <td class="num">${i.stockquantity}</td>
          <td><button class="row-del" data-id="${i.itemid}">Delete</button></td>
        </tr>`).join("")
    : `<tr><td colspan="6" class="loading-row">Ledger is empty. Add your first entry below.</td></tr>`;

  body.querySelectorAll(".row-del").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!confirm(`Delete item #${btn.dataset.id}? This cannot be undone.`)) return;
      try {
        await api(`/api/items/${btn.dataset.id}`, { method: "DELETE" });
        await refreshAll();
      } catch (e) {
        alert("Could not delete: " + e.message);
      }
    });
  });
}

async function loadAudit() {
  const rows = await api("/api/audit");
  const body = document.getElementById("auditBody");
  body.innerHTML = rows.length
    ? rows.map(r => `
        <tr>
          <td>${r.audit_id}</td>
          <td>${r.item_id ?? "—"}</td>
          <td><span class="action-badge ${r.action_type?.toLowerCase()}">${r.action_type}</span></td>
          <td class="num">${r.old_price != null ? money(r.old_price) : "—"}</td>
          <td class="num">${r.new_price != null ? money(r.new_price) : "—"}</td>
          <td>${r.changed_at ? new Date(r.changed_at).toLocaleString() : "—"}</td>
        </tr>`).join("")
    : `<tr><td colspan="6" class="loading-row">No changes recorded yet.</td></tr>`;
}

async function refreshAll() {
  await Promise.all([loadCategories(), loadItems(), loadAudit()]);
}

document.getElementById("addItemForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("addItemMsg");
  msg.textContent = "";
  msg.classList.remove("error");

  const payload = {
    name: document.getElementById("newItemName").value.trim(),
    price: parseFloat(document.getElementById("newItemPrice").value),
    stock: parseInt(document.getElementById("newItemStock").value, 10),
    category_id: parseInt(document.getElementById("newItemCategory").value, 10),
  };

  try {
    const result = await api("/api/items", { method: "POST", body: JSON.stringify(payload) });
    msg.textContent = result.message || "Added.";
    document.getElementById("addItemForm").reset();
    await refreshAll();
  } catch (err) {
    msg.textContent = err.message;
    msg.classList.add("error");
  }
});

// ---------------------------------------------------------------------
// AI Clerk chat
// ---------------------------------------------------------------------
const chatLog = document.getElementById("chatLog");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const sendBtn = chatForm.querySelector(".send-btn");

let conversationHistory = [];

function appendLog(text, cls) {
  const div = document.createElement("div");
  div.className = "log-line " + cls;
  div.textContent = text;
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
  return div;
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;

  appendLog(text, "user");
  chatInput.value = "";
  sendBtn.disabled = true;
  const thinkingLine = appendLog("thinking…", "thinking");

  try {
    const result = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message: text, history: conversationHistory }),
    });

    thinkingLine.remove();

    (result.trace || []).forEach(t => {
      appendLog(`⚙ ${t.tool}(${JSON.stringify(t.args)})`, "tool");
    });

    appendLog(result.reply, "assistant");
    conversationHistory = result.history || conversationHistory;

    // If the agent changed data, refresh the ledger panel automatically
    if ((result.trace || []).some(t => ["add_item", "update_item", "delete_item"].includes(t.tool))) {
      await refreshAll();
    }
  } catch (err) {
    thinkingLine.remove();
    appendLog("Error: " + err.message, "error");
  } finally {
    sendBtn.disabled = false;
    chatInput.focus();
  }
});

document.getElementById("resetChat").addEventListener("click", () => {
  conversationHistory = [];
  chatLog.innerHTML = `<div class="log-line system">Conversation cleared. Ask about stock, add items, or update the ledger in plain English.</div>`;
});

// ---------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------
refreshAll().catch(err => {
  document.getElementById("itemsBody").innerHTML =
    `<tr><td colspan="6" class="loading-row">Could not load ledger: ${escapeHtml(err.message)}</td></tr>`;
});
