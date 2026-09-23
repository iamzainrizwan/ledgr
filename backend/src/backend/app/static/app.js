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
  if (name === "stats") loadStats(selectedMonth);
}
$$(".tab").forEach((t) =>
  t.addEventListener("click", () => {
    location.hash = t.dataset.tab;
    activateTab(t.dataset.tab);
  })
);


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

$("#to-stats").addEventListener("click", () => {
  location.hash = "stats";
  activateTab("stats");
});

// ---- stats ----
// null = latest month with data (resolved on first load); "all" = all time
let selectedMonth = null;

const gbp = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" });
const fmtGbp = (s) => gbp.format(Number(s));

function monthLabel(m, style = "long") {
  if (!m) return "all time";
  const [y, mo] = m.split("-").map(Number);
  return new Date(y, mo - 1, 1).toLocaleDateString("en-GB", { month: style, year: style === "long" ? "numeric" : undefined });
}

const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// "vs Aug": change in a total against the previous month. for spending, down is good.
function deltaHtml(current, previous, prevMonth, downIsGood) {
  if (previous == null) return "";
  const diff = Number(current) - Number(previous);
  if (Math.abs(diff) < 0.005) return `same as ${monthLabel(prevMonth, "short")}`;
  const good = downIsGood ? diff < 0 : diff > 0;
  const arrow = diff < 0 ? "▼" : "▲";
  return `<span class="${good ? "amount-credit" : "amount-debit"}">${arrow} ${gbp.format(Math.abs(diff))}</span> vs ${monthLabel(prevMonth, "short")}`;
}

async function loadStats(month) {
  const url = month && month !== "all" ? `/stats?month=${month}` : "/stats";
  const stats = await (await fetch(url)).json();
  // first visit: open on the latest month rather than all time
  if (month === null && stats.months.length) {
    selectedMonth = stats.months[stats.months.length - 1];
    return loadStats(selectedMonth);
  }
  renderStats(stats);
}

function renderStats(stats) {
  const month = stats.month;
  $("#stats-title").textContent = month ? monthLabel(month) : "all time";

  const sel = $("#month-select");
  sel.innerHTML =
    [...stats.months].reverse().map((m) => `<option value="${m}">${monthLabel(m)}</option>`).join("") +
    `<option value="all">all time</option>`;
  sel.value = month || "all";

  const t = stats.totals;
  const p = stats.previous;
  $("#sum-spending").textContent = fmtGbp(t.spending);
  $("#sum-income").textContent = fmtGbp(t.income);
  $("#sum-net").innerHTML = fmtMoneyGbp(t.net);
  $("#delta-spending").innerHTML = p ? deltaHtml(t.spending, p.spending, p.month, true) : "";
  $("#delta-income").innerHTML = p ? deltaHtml(t.income, p.income, p.month, false) : "";
  $("#savings-rate").textContent =
    t.savings_rate == null ? "" : `${Math.round(Number(t.savings_rate) * 100)}% of income kept`;

  renderCategories(stats.categories);
  renderMonthChart(stats.by_month, month);

  $("#stats-balances").innerHTML = stats.balances
    .map((b) => `<li><span>${escapeHtml(b.name.replace("accounts:checking:", ""))}</span>${fmtMoneyGbp(b.balance)}</li>`)
    .join("");
  $("#synthetic-note").hidden = !stats.balances.some((b) => b.name === "accounts:checking:demo");
}

function fmtMoneyGbp(amountStr) {
  const n = Number(amountStr);
  return `<span class="${n < 0 ? "amount-debit" : "amount-credit"}">${gbp.format(n)}</span>`;
}

function renderCategories(categories) {
  const list = $("#cat-list");
  $("#categories-empty").hidden = categories.length > 0;
  const max = Math.max(...categories.map((c) => Number(c.total)), 0);
  list.innerHTML = categories
    .map((c) => {
      const pct = c.share == null ? "" : `${Math.round(Number(c.share) * 100)}%`;
      const width = max ? (Number(c.total) / max) * 100 : 0;
      const row = `
        <span class="cat-name">${escapeHtml(c.name)}</span>
        <span class="cat-bar"><span style="width:${width.toFixed(1)}%"></span></span>
        <span class="cat-amount">${fmtGbp(c.total)}</span>
        <span class="cat-share">${pct}</span>`;
      if (!c.subcategories.length) return `<li class="cat-row">${row}</li>`;
      const subs = c.subcategories
        .map((s) => `<li><span>${escapeHtml(s.name)}</span><span>${fmtGbp(s.total)}</span></li>`)
        .join("");
      return `<li><details class="cat-details"><summary class="cat-row">${row}</summary><ul class="cat-subs">${subs}</ul></details></li>`;
    })
    .join("");
}

// grouped bars per month (earned, spent). plain svg, no chart library.
function renderMonthChart(byMonth, selected) {
  const el = $("#month-chart");
  if (!byMonth.length) {
    el.innerHTML = "";
    return;
  }
  const W = 640, H = 180, padB = 1, padT = 12;
  const max = Math.max(...byMonth.flatMap((m) => [Number(m.income), Number(m.spending)]), 1);
  const slot = W / byMonth.length;
  const barW = Math.min(28, slot / 3.2);
  const y = (v) => padT + (H - padB - padT) * (1 - v / max);
  const bars = byMonth
    .map((m, i) => {
      const cx = slot * i + slot / 2;
      const inc = Number(m.income), sp = Number(m.spending);
      const on = m.month === selected;
      return `
        <g class="month${on ? " selected" : ""}" data-month="${m.month}" tabindex="0" role="button"
           aria-label="${monthLabel(m.month)}: earned ${gbp.format(inc)}, spent ${gbp.format(sp)}">
          <rect class="hit" x="${slot * i}" y="0" width="${slot}" height="${H}"></rect>
          <rect class="bar-income" x="${cx - barW - 2}" y="${y(inc)}" width="${barW}" height="${H - padB - y(inc)}"></rect>
          <rect class="bar-spending" x="${cx + 2}" y="${y(sp)}" width="${barW}" height="${H - padB - y(sp)}"></rect>
          <title>${monthLabel(m.month)}: earned ${gbp.format(inc)}, spent ${gbp.format(sp)}</title>
        </g>`;
    })
    .join("");
  // bars stretch with the card; labels are html so they stay readable on phones
  const labels = byMonth
    .map((m) => `<span class="${m.month === selected ? "selected" : ""}">${monthLabel(m.month, "short")}</span>`)
    .join("");
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="income and spending by month">
    <line class="baseline" x1="0" x2="${W}" y1="${H - padB}" y2="${H - padB}"></line>${bars}</svg>
    <div class="chart-labels">${labels}</div>`;
  $$(".month", el).forEach((g) => {
    const pick = () => {
      selectedMonth = g.dataset.month;
      loadStats(selectedMonth);
    };
    g.addEventListener("click", pick);
    g.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), pick()));
  });
}

$("#month-select").addEventListener("change", (e) => {
  selectedMonth = e.target.value;
  loadStats(selectedMonth);
});

// ---- reset demo ----
$("#reset-demo").addEventListener("click", async () => {
  if (!confirm("Reset the demo ledger to its seeded state? This wipes everything.")) return;
  await fetch("/demo/reset", { method: "POST" });
  skippedIds = new Set();
  selectedMonth = null;
  loadPending();
  loadBalances();
  if ($("#panel-stats").classList.contains("active")) loadStats(null);
});

loadPending();

// restore the step from the url last, once everything it touches exists
// (activateTab("stats") reads selectedMonth, declared further up)
const initialTab = location.hash.replace("#", "");
if (["upload", "review", "balances", "stats"].includes(initialTab)) activateTab(initialTab);
