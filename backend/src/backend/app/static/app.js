const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function fmtMoney(amountStr) {
  const n = Number(amountStr);
  const cls = n < 0 ? "amount-debit" : "amount-credit";
  return `<span class="${cls}">${n.toFixed(2)}</span>`;
}

const PRESETS = {
  expenses: [
    "groceries",
    "rent",
    "transport",
    "entertainment",
    "coffee",
    "dining",
    "shopping",
    "subscriptions",
    "utilities",
    "health",
    "misc",
  ],
  income: ["salary", "refund", "gift", "investment"],
  transfer: ["savings", "revolut", "other"],
};

// ---- tabs ----
function activateTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
  if (name === "review") loadPending();
  if (name === "balances") loadBalances();
}
$$(".tab").forEach((t) =>
  t.addEventListener("click", () => {
    location.hash = t.dataset.tab;
    activateTab(t.dataset.tab);
  })
);

const initialTab = location.hash.replace("#", "");
if (["upload", "review", "balances"].includes(initialTab)) activateTab(initialTab);

// ---- upload ----
$("#upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const data = new FormData(form);
  const resultEl = $("#upload-result");
  resultEl.textContent = "uploading…";
  resultEl.className = "";
  try {
    const resp = await fetch("/statements", { method: "POST", body: data });
    const body = await resp.json();
    if (!resp.ok) {
      resultEl.textContent = body.detail || "upload failed";
      resultEl.className = "result-err";
      return;
    }
    resultEl.className = "result-ok";
    resultEl.textContent =
      `staged ${body.newly_staged.length} transaction(s) for ${body.account_name}` +
      (Number(body.balance_adjustment) !== 0
        ? ` (posted a ${body.balance_adjustment} balance adjustment)`
        : "");
    form.reset();
    skippedIds = new Set();
    location.hash = "review";
    activateTab("review");
  } catch (err) {
    resultEl.className = "result-err";
    resultEl.textContent = "upload failed: " + err;
  }
});

// ---- category / subcategory presets ----
function populateCategorySelect() {
  const sel = $("#category-select");
  sel.innerHTML = "";
  for (const cat of Object.keys(PRESETS)) {
    const opt = document.createElement("option");
    opt.value = cat;
    opt.textContent = cat;
    sel.appendChild(opt);
  }
  const custom = document.createElement("option");
  custom.value = "__custom__";
  custom.textContent = "other (custom)";
  sel.appendChild(custom);
}

function populateSubcategorySelect(category) {
  const sel = $("#subcategory-select");
  sel.innerHTML = "";
  const subs = PRESETS[category] || [];
  for (const sub of subs) {
    const opt = document.createElement("option");
    opt.value = sub;
    opt.textContent = sub;
    sel.appendChild(opt);
  }
  const custom = document.createElement("option");
  custom.value = "__custom__";
  custom.textContent = "other (custom)";
  sel.appendChild(custom);
}

function updateCustomVisibility() {
  const catIsCustom = $("#category-select").value === "__custom__";
  $("#category-custom").hidden = !catIsCustom;
  $("#subcategory-select").closest("label").hidden = catIsCustom;
  $("#subcategory-custom").hidden = catIsCustom || $("#subcategory-select").value !== "__custom__";
}

$("#category-select").addEventListener("change", () => {
  if ($("#category-select").value !== "__custom__") {
    populateSubcategorySelect($("#category-select").value);
  }
  updateCustomVisibility();
});
$("#subcategory-select").addEventListener("change", updateCustomVisibility);

populateCategorySelect();
populateSubcategorySelect(Object.keys(PRESETS)[0]);

function currentCategoryValue() {
  const cat = $("#category-select").value;
  if (cat === "__custom__") {
    return $("#category-custom").value.trim();
  }
  const sub = $("#subcategory-select").value;
  const subValue = sub === "__custom__" ? $("#subcategory-custom").value.trim() : sub;
  if (!subValue) return null;
  return `${cat}:${subValue}`;
}

// try to preselect the pickers to match a suggested "category:subcategory" string
function applySuggestionToPickers(suggested) {
  if (!suggested) {
    $("#category-select").value = Object.keys(PRESETS)[0];
    populateSubcategorySelect($("#category-select").value);
    $("#category-custom").value = "";
    $("#subcategory-custom").value = "";
    updateCustomVisibility();
    return;
  }
  const [cat, ...rest] = suggested.split(":");
  const sub = rest.join(":");
  if (PRESETS[cat] && PRESETS[cat].includes(sub)) {
    $("#category-select").value = cat;
    populateSubcategorySelect(cat);
    $("#subcategory-select").value = sub;
  } else {
    $("#category-select").value = "__custom__";
    $("#category-custom").value = suggested;
  }
  updateCustomVisibility();
}

// ---- review: one transaction at a time ----
let pendingCache = [];
let skippedIds = new Set();

async function loadPending() {
  const resp = await fetch("/pending");
  pendingCache = await resp.json();
  $("#pending-count").textContent = pendingCache.length || "";
  renderReviewCard();
}

function currentQueue() {
  return pendingCache.filter((p) => !skippedIds.has(p.id));
}

function renderReviewCard() {
  const queue = currentQueue();
  const isEmpty = queue.length === 0;
  $("#review-empty").hidden = !isEmpty;
  $("#review-card").hidden = isEmpty;
  if (isEmpty) return;

  const p = queue[0];
  $("#review-index").textContent = "1";
  $("#review-total").textContent = queue.length;
  $("#txn-date").textContent = p.date;
  $("#txn-account").textContent = p.account_name;
  $("#txn-description").textContent = p.description;
  $("#txn-amount").innerHTML = fmtMoney(p.amount);
  $("#txn-suggestion").hidden = !p.suggested_category;
  $("#txn-suggestion").textContent = p.suggested_category
    ? `suggested: ${p.suggested_category}`
    : "";

  applySuggestionToPickers(p.suggested_category);
}

async function finishCurrentAndAdvance(action) {
  const queue = currentQueue();
  if (queue.length === 0) return;
  const current = queue[0];

  if (action === "categorize") {
    const category = currentCategoryValue();
    if (!category) {
      alert("Pick or enter a category first.");
      return;
    }
    await fetch(`/pending/${current.id}/categorize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category }),
    });
    await loadPending();
  } else {
    skippedIds.add(current.id);
    renderReviewCard();
  }

  if (currentQueue().length === 0) {
    location.hash = "balances";
    activateTab("balances");
  }
}

$("#categorize-txn").addEventListener("click", () => finishCurrentAndAdvance("categorize"));
$("#skip-txn").addEventListener("click", () => finishCurrentAndAdvance("skip"));

// ---- balances ----
async function loadBalances() {
  const resp = await fetch("/accounts");
  const accounts = await resp.json();
  const body = $("#balances-body");
  body.innerHTML = "";
  for (const a of accounts) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${a.name}</td><td>${fmtMoney(a.balance)}</td>`;
    body.appendChild(tr);
  }
}

// ---- reset demo ----
$("#reset-demo").addEventListener("click", async () => {
  if (!confirm("Reset the demo ledger to its seeded state? This wipes everything.")) return;
  await fetch("/demo/reset", { method: "POST" });
  skippedIds = new Set();
  loadPending();
  loadBalances();
});

loadPending();
