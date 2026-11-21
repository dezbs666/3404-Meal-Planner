/* global dlgRecipe, dlgView, dlgPlanDays, dlgImport */

const $ = (id) => document.getElementById(id);
const state = {
  recipes: [],
  weekStart: null,
  plan: null,
  planChoiceRecipe: null,
  viewingRecipe: null,
  editingRecipe: null,
  hideChecked: false,
};

function toast(msg, isError) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.toggle("error", Boolean(isError));
  el.classList.remove("hidden");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), 3200);
}

async function api(path, options = {}) {
  if (options.body && typeof options.body !== "string") {
    options.body = JSON.stringify(options.body);
  }
  options.headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const res = await fetch(path, options);
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) throw new Error((data && data.error) || `Request failed (${res.status})`);
  return data;
}

/* ---------- tabs ---------- */
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === btn));
    ["recipes", "planner", "list"].forEach((t) => {
      $(`tab-${t}`).classList.toggle("hidden", t !== btn.dataset.tab);
    });
    refreshTab(btn.dataset.tab);
  });
});

function refreshTab(tab) {
  if (tab === "recipes") loadRecipes();
  if (tab === "planner") loadPlan();
  if (tab === "list") loadList();
}

/* ---------- recipes ---------- */
async function loadRecipes() {
  const q = $("recipeSearch").value.trim();
  state.recipes = await api(`/api/recipes${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  renderRecipes();
}

function renderRecipes() {
  const grid = $("recipeGrid");
  grid.innerHTML = "";
  $("recipeEmpty").classList.toggle("hidden", state.recipes.length > 0);
  for (const r of state.recipes) {
    const card = document.createElement("div");
    card.className = "recipe-card";
    const tags = r.tags ? r.tags.split(",").map((t) => t.trim()).filter(Boolean) : [];
    card.innerHTML = `
      <div class="title"></div>
      <div class="meta"></div>
      ${tags.length ? `<div class="tags">${tags.map((t) => `<span class="tagpill"></span>`).join("")}</div>` : ""}
    `;
    card.querySelector(".title").textContent = r.title;
    card.querySelector(".meta").textContent =
      `Serves ${r.servings}` + (r.total_time ? ` · ${r.total_time}` : r.cook_time ? ` · ${r.cook_time}` : "");
    card.querySelectorAll(".tagpill").forEach((el, i) => { el.textContent = tags[i]; });
    card.addEventListener("click", () => viewRecipe(r.id));
    grid.appendChild(card);
  }
}

$("recipeSearch").addEventListener("input", () => loadRecipes());
$("btnAddRecipe").addEventListener("click", () => openRecipeDialog(null));
$("btnImportRecipe").addEventListener("click", () => { $("importUrl").value = ""; $("dlgImport").showModal(); });

function esc(s) {
  const div = document.createElement("div");
  div.textContent = s == null ? "" : String(s);
  return div.innerHTML;
}

function openRecipeDialog(recipe) {
  state.editingRecipe = recipe;
  $("dlgRecipeTitle").textContent = recipe ? "Edit recipe" : "Add recipe";
  const f = $("formRecipe");
  f.reset();
  if (recipe) {
    f.title.value = recipe.title;
    f.servings.value = recipe.servings;
    f.prep_time.value = recipe.prep_time;
    f.cook_time.value = recipe.cook_time;
    f.ingredients.value = recipe.ingredients.join("\n");
    f.instructions.value = recipe.instructions;
    f.tags.value = recipe.tags;
    f.source_url.value = recipe.source_url;
  }
  $("dlgRecipe").showModal();
}

$("btnCancelRecipe").addEventListener("click", () => $("dlgRecipe").close());

$("formRecipe").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const payload = {
    title: f.title.value,
    servings: parseInt(f.servings.value, 10) || 4,
    prep_time: f.prep_time.value,
    cook_time: f.cook_time.value,
    ingredients: f.ingredients.value.split("\n").map((s) => s.trim()).filter(Boolean),
    instructions: f.instructions.value,
    tags: f.tags.value,
    source_url: f.source_url.value,
  };
  try {
    if (state.editingRecipe) {
      await api(`/api/recipes/${state.editingRecipe.id}`, { method: "PUT", body: payload });
      toast("Recipe updated");
    } else {
      await api("/api/recipes", { method: "POST", body: payload });
      toast("Recipe saved");
    }
    $("dlgRecipe").close();
    loadRecipes();
  } catch (err) {
    toast(err.message, true);
  }
});

$("btnDoImport").addEventListener("click", async () => {
  const url = $("importUrl").value.trim();
  if (!url) return;
  const btn = $("btnDoImport");
  btn.disabled = true;
  btn.textContent = "Importing…";
  try {
    const recipe = await api("/api/import", { method: "POST", body: { url } });
    $("dlgImport").close();
    toast(`Imported “${recipe.title}”`);
    document.querySelector('.tab[data-tab="recipes"]').click();
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Import";
  }
});

async function viewRecipe(id) {
  const r = await api(`/api/recipes/${id}`);
  state.viewingRecipe = r;
  let html = `<h2 class="v-title">${esc(r.title)}</h2>
    <div class="v-meta">Serves ${r.servings}` +
    (r.prep_time ? ` · prep ${r.prep_time}` : "") + (r.cook_time ? ` · cook ${r.cook_time}` : "") +
    (r.total_time ? ` · total ${r.total_time}` : "") + `</div>`;
  if (r.source_url) {
    html += `<a class="v-link" href="${esc(r.source_url)}" target="_blank" rel="noopener">Original page ↗</a>`;
  }
  html += `<h4>Ingredients</h4><ul>${r.ingredients.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`;
  if (r.instructions) {
    html += `<h4>Instructions</h4><ol>${r.instructions
      .split(/\n+/).filter(Boolean).map((s) => `<li>${esc(s)}</li>`).join("")}</ol>`;
  }
  if (r.notes) html += `<div class="v-notes">${esc(r.notes)}</div>`;
  $("viewBody").innerHTML = html;
  $("dlgView").showModal();
}

$("btnEditRecipe").addEventListener("click", () => {
  if (!state.viewingRecipe) return;
  dlgView.close();
  openRecipeDialog(state.viewingRecipe);
});

$("btnPlanRecipe").addEventListener("click", () => {
  if (!state.viewingRecipe) return;
  openPlanDays(state.viewingRecipe);
});

$("btnDeleteRecipe").addEventListener("click", async () => {
  const r = state.viewingRecipe;
  if (!r || !confirm(`Delete “${r.title}”? This also removes it from the meal plan.`)) return;
  await api(`/api/recipes/${r.id}`, { method: "DELETE" });
  $("dlgView").close();
  toast("Recipe deleted");
  loadRecipes();
});

/* ---------- planner ---------- */
$("weekPrev").addEventListener("click", () => shiftWeek(-7));
$("weekNext").addEventListener("click", () => shiftWeek(7));
$("weekToday").addEventListener("click", () => { state.weekStart = null; loadPlan(); });

function shiftWeek(days) {
  if (!state.weekStart) {
    const d = new Date();
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    state.weekStart = d;
  }
  state.weekStart.setDate(state.weekStart.getDate() + days);
  loadPlan();
}

function fmtWeekLabel(start) {
  const opts = { month: "short", day: "numeric" };
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  return `${start.toLocaleDateString(undefined, opts)} – ${end.toLocaleDateString(undefined, opts)}`;
}

async function loadPlan() {
  const weekParam = state.weekStart ? weekKey(state.weekStart) : "";
  state.plan = await api(`/api/plan${weekParam ? `?week=${weekParam}` : ""}`);
  renderPlan();
}

function weekKey(d) {
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function renderPlan() {
  const start = new Date(state.plan.week_start + "T12:00:00");
  $("weekLabel").textContent = fmtWeekLabel(start);
  const today = weekKey(new Date());
  const wrap = $("planDays");
  wrap.innerHTML = "";
  const options = state.recipes.length
    ? state.recipes
    : [];
  for (const day of state.plan.days) {
    const div = document.createElement("div");
    div.className = "plan-day" + (day.date === today ? " today" : "");
    const dt = new Date(day.date + "T12:00:00");
    const dayName = dt.toLocaleDateString(undefined, { weekday: "long" });
    const dateLabel = dt.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    let inner = `<div class="day-head"><span class="day-name">${esc(dayName)}</span><span class="day-date">${esc(dateLabel)}</span></div>`;
    for (const entry of day.entries) {
      inner += `<div class="plan-entry" data-plan="${entry.plan_id}">
        <span class="name"></span>
        <span class="serv">serves ${entry.planned_servings}</span>
        <button class="remove" title="Remove from plan">✕</button>
      </div>`;
    }
    inner += `<select class="pick"><option value="">+ Add a recipe…</option>${
      options.map((r) => `<option value="${r.id}">${esc(r.title)}</option>`).join("")
    }</select>`;
    div.innerHTML = inner;
    div.querySelectorAll(".plan-entry").forEach((row) => {
      const planId = row.dataset.plan;
      const entry = day.entries.find((e) => String(e.plan_id) === String(planId));
      row.querySelector(".name").textContent = entry.title;
      row.querySelector(".name").addEventListener("click", () => viewRecipe(entry.recipe_id));
      row.querySelector(".remove").addEventListener("click", async () => {
        await api(`/api/plan/${planId}`, { method: "DELETE" });
        loadPlan();
      });
    });
    const pick = div.querySelector(".pick");
    pick.addEventListener("change", async () => {
      if (!pick.value) return;
      await api("/api/plan", { method: "POST", body: { date: day.date, recipe_id: parseInt(pick.value, 10) } });
      pick.value = "";
      toast("Added to plan");
      loadPlan();
    });
    wrap.appendChild(div);
  }
  if (!state.recipes.length) {
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = "Add or import recipes first, then assign them to days here.";
    wrap.appendChild(note);
  }
}

$("btnBuildList").addEventListener("click", async () => {
  const res = await api("/api/list/build", { method: "POST" });
  toast(res.added || res.updated
    ? `Shopping list updated (${res.added} added, ${res.updated} merged)`
    : "Plan is empty — add recipes to days first");
  document.querySelector('.tab[data-tab="list"]').click();
});

function openPlanDays(recipe) {
  state.planChoiceRecipe = recipe;
  $("planServings").value = recipe.servings;
  const wrap = $("planDayChoices");
  wrap.innerHTML = "";
  const start = new Date((state.plan ? state.plan.week_start : weekKey(new Date())) + "T12:00:00");
  for (let i = 0; i < 7; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "planChoice ghost";
    btn.innerHTML = `<b></b><span class="hint"></span>`;
    btn.children[0].textContent = d.toLocaleDateString(undefined, { weekday: "long" });
    btn.children[1].textContent = d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    btn.addEventListener("click", async () => {
      await api("/api/plan", {
        method: "POST",
        body: {
          date: weekKey(d),
          recipe_id: recipe.id,
          servings: parseInt($("planServings").value, 10) || recipe.servings,
        },
      });
      dlgPlanDays.close();
      dlgView.close();
      state.weekStart = start;
      toast(`Added to ${btn.children[1].textContent}`);
      document.querySelector('.tab[data-tab="planner"]').click();
    });
    wrap.appendChild(btn);
  }
  dlgPlanDays.showModal();
}

/* ---------- shopping list ---------- */
async function loadList() {
  const grouped = await api("/api/list");
  renderList(grouped);
  const count = Object.values(grouped).flat().filter((i) => !i.checked).length;
  const badge = $("listBadge");
  badge.textContent = count;
  badge.classList.toggle("hidden", count === 0);
  const total = Object.values(grouped).flat().length;
  $("listEmpty").classList.toggle("hidden", total > 0);
}

function qtyLabel(item) {
  const q = item.qty || "";
  if (q && item.unit) return `${q} ${item.unit}`;
  return item.unit || q || "";
}

function renderList(grouped) {
  const wrap = $("shoppingList");
  wrap.innerHTML = "";
  for (const [category, items] of Object.entries(grouped)) {
    if (state.hideChecked) {
      const visible = items.filter((i) => !i.checked);
      if (!visible.length) continue;
    }
    const cat = document.createElement("div");
    cat.className = "cat";
    cat.innerHTML = `<h3>${esc(category)}</h3>`;
    for (const item of items) {
      const row = document.createElement("div");
      row.className = "list-item" + (item.checked ? " checked" : "");
      row.innerHTML = `
        <button class="check" title="Toggle">✓</button>
        <span class="label"><span class="name"></span></span>
        <span class="qty"></span>
        ${item.source === "plan" ? '<span class="src" title="Comes from your meal plan">plan</span>' : ""}
        <button class="del" title="Remove">✕</button>`;
      row.querySelector(".name").textContent = item.name;
      row.querySelector(".qty").textContent = qtyLabel(item);
      row.querySelector(".check").addEventListener("click", async () => {
        await api(`/api/list/${item.id}`, { method: "PATCH" });
        loadList();
      });
      row.querySelector(".del").addEventListener("click", async () => {
        await api(`/api/list/${item.id}`, { method: "DELETE" });
        loadList();
      });
      cat.appendChild(row);
    }
    wrap.appendChild(cat);
  }
}

async function quickAdd() {
  const input = $("quickAdd");
  const value = input.value.trim();
  if (!value) return;
  input.value = "";
  await api("/api/list", { method: "POST", body: { name: value } });
  loadList();
}
$("btnQuickAdd").addEventListener("click", quickAdd);
$("quickAdd").addEventListener("keydown", (e) => { if (e.key === "Enter") quickAdd(); });

$("btnHideChecked").addEventListener("click", (e) => {
  state.hideChecked = !state.hideChecked;
  e.target.textContent = state.hideChecked ? "Show checked" : "Hide checked";
  loadList();
});

$("btnClearChecked").addEventListener("click", async () => {
  const res = await api("/api/list/clear-checked", { method: "POST" });
  toast(res.removed ? `Removed ${res.removed} item(s)` : "Nothing checked off");
  loadList();
});

$("btnClearAll").addEventListener("click", async () => {
  if (!confirm("Clear the whole shopping list?")) return;
  const grouped = await api("/api/list");
  const all = Object.values(grouped).flat();
  await Promise.all(all.map((i) => api(`/api/list/${i.id}`, { method: "DELETE" })));
  loadList();
});

/* ---------- boot ---------- */
async function boot() {
  state.recipes = await api("/api/recipes");
  loadRecipes();
  loadList();
}
boot();
