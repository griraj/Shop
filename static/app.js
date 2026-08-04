// Helpers
function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = String(str ?? "");
  return d.innerHTML;
}

function money(n) {
  return "PKR " + Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

// Drawer open/close
const drawer = document.getElementById("drawer");
const drawerTab = document.getElementById("drawerTab");
const drawerScrim = document.getElementById("drawerScrim");
const drawerClose = document.getElementById("drawerClose");

function openDrawer() {
  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
  drawerTab.setAttribute("aria-expanded", "true");
  drawerScrim.classList.add("show");
}
function closeDrawer() {
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
  drawerTab.setAttribute("aria-expanded", "false");
  drawerScrim.classList.remove("show");
}
drawerTab.addEventListener("click", () => {
  drawer.classList.contains("open") ? closeDrawer() : openDrawer();
});
drawerClose.addEventListener("click", closeDrawer);
drawerScrim.addEventListener("click", closeDrawer);

// Nav + hero actions
function scrollToClerk() {
  document.getElementById("receipt").scrollIntoView({ behavior: "smooth", block: "center" });
  document.getElementById("chatInput").focus();
}
document.getElementById("navOpenDrawer").addEventListener("click", openDrawer);
document.getElementById("navLedger").addEventListener("click", (e) => { e.preventDefault(); openDrawer(); });
document.getElementById("navClerk").addEventListener("click", (e) => { e.preventDefault(); scrollToClerk(); });
document.getElementById("navTryDemo").addEventListener("click", scrollToClerk);
document.getElementById("heroEnter").addEventListener("click", () => {
  document.querySelector(".preview-frame").scrollIntoView({ behavior: "smooth", block: "center" });
});
document.getElementById("heroTalk").addEventListener("click", scrollToClerk);

// Drawer inner tabs
document.querySelectorAll(".dtab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".dtab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".drawer-panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("dpanel-" + btn.dataset.tab).classList.add("active");
  });
});

// Ledger data (items / categories / audit)
let categoriesCache = [];

async function loadCategories() {
  categoriesCache = await api("/api/categories");
  const list = document.getElementById("categoriesList");
  list.innerHTML = categoriesCache.length
    ? categoriesCache.map(c => `
        <li>
          <span>${escapeHtml(c.categoryname)}</span>
          <span class="c-count">${c.item_count} item${c.item_count === 1 ? "" : "s"}</span>
        </li>`).join("")
    : `<li class="tag-empty">No categories yet.</li>`;

  const select = document.getElementById("newItemCategory");
  select.innerHTML = categoriesCache.map(c => `<option value="${c.categoryid}">${escapeHtml(c.categoryname)}</option>`).join("");
}

async function loadItems() {
  const items = await api("/api/items");
  const grid = document.getElementById("itemsGrid");
  grid.innerHTML = items.length
    ? items.map(i => {
        const cleanName = String(i.itemname).replace(/\s*\d+\s*$/, "").trim();
        return `
        <div class="tag-card" data-id="${i.itemid}">
          <span class="tag-num">${i.itemid}</span>
          <div class="tag-info">
            <div class="tag-name">${escapeHtml(cleanName)}</div>
            <div class="tag-meta">${escapeHtml(i.categoryname || "uncategorized")} · stock ${i.stockquantity}</div>
          </div>
          <div class="tag-price">${money(i.price)}</div>
          <button class="tag-del" data-id="${i.itemid}">Del</button>
        </div>`;
      }).join("")
    : `<div class="tag-empty">No tags hanging yet. Write one below.</div>`;

  grid.querySelectorAll(".tag-del").forEach(btn => {
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
  const list = document.getElementById("auditList");
  list.innerHTML = rows.length
    ? rows.map(r => `
        <li>
          <span class="audit-tag ${r.action_type?.toLowerCase()}">${r.action_type}</span>
          item #${r.item_id ?? "—"}
          ${r.old_price != null ? `&nbsp;${money(r.old_price)} &rarr;` : ""}
          ${r.new_price != null ? `&nbsp;${money(r.new_price)}` : ""}
          <div class="audit-when">${r.changed_at ? new Date(r.changed_at).toLocaleString() : ""}</div>
        </li>`).join("")
    : `<li class="tag-empty">No changes recorded yet.</li>`;
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
    msg.textContent = result.message || "Tag hung.";
    document.getElementById("addItemForm").reset();
    await refreshAll();
  } catch (err) {
    msg.textContent = err.message;
    msg.classList.add("error");
  }
});

// AI Clerk — receipt-printed conversation
const receiptLines = document.getElementById("receiptLines");
const receiptScroll = document.getElementById("receiptScroll");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");

let conversationHistory = [];

function printLine(text, cls) {
  const div = document.createElement("div");
  div.className = "r-line " + cls;
  div.textContent = text;
  receiptLines.appendChild(div);
  receiptScroll.scrollTop = receiptScroll.scrollHeight;
  return div;
}

if (chatForm && chatInput && sendBtn) {
  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;

    printLine(text, "you");
    chatInput.value = "";
    sendBtn.disabled = true;
    const thinkingLine = printLine("printing...", "thinking");

    try {
      const result = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({ message: text, history: conversationHistory }),
      });

      thinkingLine.remove();
      if (!result || typeof result !== "object") {
        throw new Error("Invalid chat response");
      }

      (result.trace || []).forEach(t => {
        printLine(`${t.tool}(${JSON.stringify(t.args)})`, "tool");
      });

      printLine(result.reply ?? "(no response)", "clerk");
      conversationHistory = Array.isArray(result.history) ? result.history : conversationHistory;

      if ((result.trace || []).some(t => ["add_item", "update_item", "delete_item"].includes(t.tool))) {
        await refreshAll();
      }
    } catch (err) {
      thinkingLine.remove();
      printLine(err.message, "error");
    } finally {
      sendBtn.disabled = false;
      chatInput.focus();
    }
  });
}

// Init
refreshAll().catch(err => {
  document.getElementById("itemsGrid").innerHTML =
    `<div class="tag-empty">Could not load ledger: ${escapeHtml(err.message)}</div>`;
});