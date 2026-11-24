/* global dlgRecipe, dlgView, dlgPlanDays, dlgImport, dlgSuggest, dlgHidden */

const $ = (id) => document.getElementById(id);
const state = {
  recipes: [],
  weekStart: null,
  plan: null,
  planChoiceRecipe: null,
  viewingRecipe: null,
  editingRecipe: null,
  hideChecked: false,
  currentSuggestion: null,
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
    ["recipes", "planner", "list", "ideas"].forEach((t) => {
      $(`tab-${t}`).classList.toggle("hidden", t !== btn.dataset.tab);
    });
    refreshTab(btn.dataset.tab);
  });
});

function refreshTab(tab) {
  if (tab === "recipes") loadRecipes();
  if (tab === "planner") loadPlan();
  if (tab === "list") loadList();
  if (tab === "ideas") loadIdeas();
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

/* ---------- ideas (suggestions) ---------- */
const EQUIPMENT_NAMES = {
  oven: "Oven",
  skillet: "Cast-iron skillet",
  pot: "Pot",
  "instant pot": "Instant Pot",
  "sous vide": "Sous vide",
};
const IDEA_BATCH = 9;
let ideaEquipment = "";
let ideasAll = [];
let ideasWeb = [];
let ideasNotice = "";
let hiddenCount = 0;

["fGf", "fNoBeef", "fNs", "fComplete"].forEach((id) => {
  $(id).addEventListener("change", loadIdeas);
});
$("equipChips").querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    ideaEquipment = chip.dataset.eq;
    $("equipChips").querySelectorAll(".chip").forEach((c) => c.classList.toggle("active", c === chip));
    loadIdeas();
  });
});

function seedFromString(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function seededShuffle(list, seed) {
  const arr = list.slice();
  let a = seed;
  const rnd = () => {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function ideasWeekKey() {
  const d = new Date();
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function ideaShuffleCount() {
  const wk = ideasWeekKey();
  if (localStorage.getItem("ideasWeek") !== wk) {
    localStorage.setItem("ideasWeek", wk);
    localStorage.setItem("ideasShuffles", "0");
    return 0;
  }
  return parseInt(localStorage.getItem("ideasShuffles") || "0", 10);
}

async function loadIdeas() {
  const params = new URLSearchParams();
  if ($("fGf").checked) params.set("gf", "1");
  if ($("fNoBeef").checked) params.set("no_beef", "1");
  if ($("fNs").checked) params.set("low_nightshade", "1");
  if ($("fComplete").checked) params.set("complete", "1");
  params.set("equipment", ideaEquipment);
  ideasAll = await api(`/api/suggestions?${params}`);
  ideasWeb = [];
  ideasNotice = "";
  try {
    const web = await api(`/api/suggestions/web?${params}`);
    ideasWeb = web.items;
    ideasNotice = web.notice;
  } catch (e) {
    ideasNotice = "Couldn't reach the recipe web right now.";
  }
  const hidden = await api("/api/suggestions/hidden");
  hiddenCount = hidden.length;
  $("btnHiddenIdeas").textContent = `Hidden ideas (${hiddenCount})`;
  renderIdeasBatch();
}

function renderIdeasBatch() {
  const seed = seedFromString(`${ideasWeekKey()}:${ideaShuffleCount()}`);
  const batch = seededShuffle(ideasAll, seed).slice(0, IDEA_BATCH);
  $("ideaGrid").innerHTML = "";
  renderIdeas(batch);
  renderWeb();
  $("ideaCount").textContent = ideasAll.length
    ? `Showing ${batch.length} of ${ideasAll.length} ideas`
    : "";
}

function buildIdeaCard(s, web) {
  const card = document.createElement("div");
  card.className = "recipe-card" + (s.perfect ? "" : " adaptable");
  card.innerHTML = `
    <div class="title"></div>
    <div class="meta"></div>
    <div class="pills"></div>
    <div class="tags">${(s.tags || []).map(() => `<span class="tagpill"></span>`).join("")}</div>
  `;
  const label = [];
  if (web) label.push("\ud83c\udf10");
  label.push(`Serves ${s.servings}`);
  if (s.total_time) label.push(s.total_time);
  if (web) label.push("TheMealDB");
  else label.push(s.equipment.join(", "));
  card.querySelector(".title").textContent = s.title;
  card.querySelector(".meta").textContent = label.filter(Boolean).join(" · ");
  const pills = card.querySelector(".pills");
    if (s.complete) {
      const p = document.createElement("div");
      p.className = "completepill";
      p.textContent = "complete meal · includes veggies";
      pills.appendChild(p);
    }
  if (!s.perfect) {
    const p = document.createElement("div");
    p.className = "swappill";
    p.textContent = "needs a small tweak";
    pills.appendChild(p);
  }
  card.querySelectorAll(".tagpill").forEach((el, i) => { el.textContent = s.tags[i]; });
  card.addEventListener("click", () => viewSuggestion(s));
  return card;
}

function renderIdeas(ideas) {
  $("ideaEmpty").classList.toggle("hidden", ideasAll.length > 0);
  const grid = $("ideaGrid");
  for (const s of ideas) grid.appendChild(buildIdeaCard(s, false));
}

function renderWeb() {
  const grid = $("ideaGrid");
  const head = document.createElement("div");
  if (ideasNotice || !ideasWeb.length) {
    head.innerHTML = `<div class="w3-head">\ud83c\udf10 From the web</div><p class="hint"></p>`;
    head.querySelector(".hint").textContent =
      ideasNotice || "No new web recipes passed the filters \u2014 try again shortly.";
    grid.appendChild(head);
    return;
  }
  head.innerHTML = `<div class="w3-head">\ud83c\udf10 Fresh from the web \u00b7 TheMealDB</div>
    <p class="hint">Pulled from the internet and auto-checked against your filters \u2014 always double-check labels for gluten.</p>`;
  grid.appendChild(head);
  for (const s of ideasWeb) grid.appendChild(buildIdeaCard(s, true));
}

$("btnNewIdeas").addEventListener("click", () => {
  const n = ideaShuffleCount() + 1;
  localStorage.setItem("ideasShuffles", String(n));
  renderIdeasBatch();
});

function viewSuggestion(s) {
  state.currentSuggestion = s;
  let html = `<h2 class="v-title"></h2>
    <div class="v-meta">Serves ${s.servings} · ${s.total_time}</div>
    <h4>You'll need</h4><div class="v-equip"></div>
    <h4>Ingredients</h4><ul>${s.ingredients.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>
    <h4>Instructions</h4><ol>${s.instructions.map((i) => `<li>${esc(i)}</li>`).join("")}</ol>`;
  const notes = [];
  if (s.gf && s.gf !== true) notes.push(`Gluten-free: ${s.gf}`);
  if (s.beef && s.beef_swap) notes.push(`No beef: ${s.beef_swap}`);
  if (s.ns_note) notes.push(s.ns_note);
  if (notes.length) html += `<div class="v-notes swap-notes"><b>Good to know</b>${notes.map((n) => `<div>• ${esc(n)}</div>`).join("")}</div>`;
  else html += `<div class="v-notes ok-note">Fits all your filters as written ✓</div>`;
  if (s.source_url) {
    html = `<a class="v-link" href="${esc(s.source_url)}" target="_blank" rel="noopener">Original web page ↗</a>` + html;
  }
  const body = $("suggestBody");
  body.innerHTML = html;
  body.querySelector(".v-title").textContent = s.title;
  body.querySelector(".v-equip").textContent = s.equipment && s.equipment.length
    ? s.equipment.map((e) => EQUIPMENT_NAMES[e] || e).join(" · ")
    : "check the recipe site for equipment";
  $("dlgSuggest").showModal();
}

$("btnSaveSuggestion").addEventListener("click", async () => {
  const s = state.currentSuggestion;
  if (!s) return;
  const notes = [];
  if (s.gf && s.gf !== true) notes.push(`Gluten-free: ${s.gf}`);
  if (s.beef && s.beef_swap) notes.push(`No beef: ${s.beef_swap}`);
  if (s.ns_note) notes.push(s.ns_note);
  try {
    await api("/api/recipes", {
      method: "POST",
      body: {
        title: s.title,
        servings: s.servings,
        total_time: s.total_time,
        ingredients: s.ingredients,
        instructions: s.instructions.join("\n"),
        tags: [...(s.tags || []), "suggestion"].join(", "),
        notes: notes.join(" "),
        source_url: s.source_url || "",
      },
    });
    dlgSuggest.close();
    toast(`Saved “${s.title}” to your recipes`);
    document.querySelector('.tab[data-tab="recipes"]').click();
  } catch (err) {
    toast(err.message, true);
  }
});

$("btnHideSuggestion").addEventListener("click", async () => {
  const s = state.currentSuggestion;
  if (!s) return;
  await api("/api/suggestions/hide", { method: "POST", body: { title: s.title } });
  dlgSuggest.close();
  toast(`Hidden “${s.title}” — find it under Hidden ideas if you change your mind`);
  loadIdeas();
});

$("btnHiddenIdeas").addEventListener("click", async () => {
  const titles = await api("/api/suggestions/hidden");
  const wrap = $("hiddenList");
  wrap.innerHTML = "";
  if (!titles.length) {
    const p = document.createElement("p");
    p.className = "hint";
    p.textContent = "Nothing hidden yet. Pick an idea, then tap \u201cNot interested\u201d to tuck it away.";
    wrap.appendChild(p);
  }
  for (const title of titles) {
    const row = document.createElement("div");
    row.className = "hidden-row";
    const name = document.createElement("span");
    name.textContent = title;
    const btn = document.createElement("button");
    btn.className = "ghost";
    btn.textContent = "Bring back";
    btn.addEventListener("click", async () => {
      await api("/api/suggestions/unhide", { method: "POST", body: { title } });
      openHiddenIdeas();
    });
    row.append(name, btn);
    wrap.appendChild(row);
  }
  $("dlgHidden").showModal();
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
    cat.dataset.cat = category;
    cat.innerHTML = `<h3>${esc(category)}</h3>`;
    for (const item of items) {
      const row = document.createElement("div");
      row.className = "list-item" + (item.checked ? " checked" : "");
      row.dataset.id = item.id;
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

/* touch & hold (or click) an item, drag it onto another section header */
(() => {
  const wrap = $("shoppingList");
  let active = false, ghost = null, heldRow = null, hoverCat = null, timer = null;

  function clearGhost() {
    if (ghost) { ghost.remove(); ghost = null; }
    if (heldRow) { heldRow.classList.remove("dragging"); heldRow = null; }
    if (hoverCat) { hoverCat.classList.remove("drop-target"); hoverCat = null; }
  }

  function resolveCat(x, y) {
    const el = document.elementFromPoint(x, y);
    return (el && el.closest) ? el.closest(".cat") : null;
  }

  wrap.addEventListener("pointerdown", (e) => {
    const row = e.target.closest(".list-item");
    if (!row || e.target.closest(".check, .del")) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;
    heldRow = row;
    active = false;
    const startX = e.clientX, startY = e.clientY;
    const hold = e.pointerType === "mouse" ? 0 : 330;
    if (hold === 0) activate(startX, startY);
    else timer = setTimeout(() => activate(startX, startY), hold);

    function activate(x, y) {
      if (!heldRow || active) return;
      timer = null;
      active = true;
      ghost = document.createElement("div");
      ghost.className = "drag-ghost";
      ghost.textContent = heldRow.querySelector(".name").textContent;
      document.body.appendChild(ghost);
      heldRow.classList.add("dragging");
      ghost.style.left = x + "px";
      ghost.style.top = y + "px";
    }

    const move = (ev) => {
      if (!active) {
        if (timer && Math.hypot(ev.clientX - startX, ev.clientY - startY) > 10) {
          clearTimeout(timer);
          timer = null;
        }
        return;
      }
      ev.preventDefault();
      ghost.style.left = ev.clientX + "px";
      ghost.style.top = ev.clientY + "px";
      const cat = resolveCat(ev.clientX, ev.clientY);
      if (hoverCat && hoverCat !== cat) hoverCat.classList.remove("drop-target");
      hoverCat = cat;
      if (cat) cat.classList.add("drop-target");
    };
    const onTouchMove = (ev) => { if (active) ev.preventDefault(); };
    const finish = async () => {
      if (timer) { clearTimeout(timer); timer = null; }
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", finish);
      document.removeEventListener("touchmove", onTouchMove);
      if (!active) return;
      const row = heldRow, target = hoverCat;
      const itemId = row.dataset.id;
      dropCleanup();
      if (target && target.dataset.cat) {
        try {
          await api(`/api/list/${itemId}/move`, { method: "PATCH", body: { category: target.dataset.cat } });
          toast(`Moved to ${target.dataset.cat}`);
        } catch (err) {
          toast(err.message, true);
        }
        loadList();
      }
    };
    function dropCleanup() {
      active = false;
      clearGhost();
    }
    window.addEventListener("pointermove", move, { passive: false });
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", finish);
    document.addEventListener("touchmove", onTouchMove, { passive: false });
  });
})();

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
