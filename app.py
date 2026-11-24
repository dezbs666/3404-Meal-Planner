import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta

from flask import Flask, g, jsonify, render_template, request

from quantities import (
    UNIT_FAMILIES, best_display_unit, format_amount, guess_category,
    merge_ingredient_name, parse_quantity, unit_family,
)
from recipe_import import fetch_recipe, extract_recipe
from suggestions import SUGGESTIONS

DB_PATH = os.environ.get(
    "MEALPLANNER_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "mealplanner.db"),
)

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    servings INTEGER NOT NULL DEFAULT 4,
    ingredients TEXT NOT NULL,
    instructions TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    image TEXT DEFAULT '',
    prep_time TEXT DEFAULT '',
    cook_time TEXT DEFAULT '',
    total_time TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meal_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_date TEXT NOT NULL,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    servings INTEGER NOT NULL DEFAULT 4,
    UNIQUE(plan_date, recipe_id)
);

CREATE TABLE IF NOT EXISTS shopping_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    qty TEXT DEFAULT '',
    unit TEXT DEFAULT '',
    amount REAL,
    category TEXT DEFAULT 'Other',
    source TEXT DEFAULT 'custom',
    checked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(name, unit)
);

CREATE TABLE IF NOT EXISTS hidden_suggestions (
    title TEXT PRIMARY KEY
);
"""

with sqlite3.connect(DB_PATH) as _init:
    _init.executescript(SCHEMA)


@app.get("/")
def index():
    return render_template("index.html")


def parse_ingredient_line(line):
    text = line.strip()
    text = re.sub(r"^\s*[-*•]\s*", "", text)
    qty_part, _, rest = text.partition(" ")
    lead_amount = None
    parsed_lead = parse_quantity(text)
    if parsed_lead.amount is not None:
        lead_amount = parsed_lead.amount
        remainder = (parsed_lead.unit + " " + parsed_lead.rest).strip()
    else:
        remainder = text
    remainder = remainder.strip()

    unit = ""
    amount = lead_amount
    from quantities import normalize_unit, UNIT_ALIASES
    known_units = set(UNIT_ALIASES.values())
    match = re.match(r"^([\d½¼¾⅓⅔./\s]+)\s*([a-zA-Z][a-zA-Z. ]*?)\s+(.*)$", text + " ")
    if match:
        candidate = match.group(2).strip()
        normalized = normalize_unit(candidate)
        if normalized and normalized in known_units:
            candidate_qty = parse_quantity(match.group(1).strip())
            if candidate_qty.amount is not None:
                amount = candidate_qty.amount
                unit = normalized
                remainder = match.group(3).strip()

    remainder = re.sub(r"[\(\[（].*?[\)\]）]", "", remainder).strip()
    remainder = re.sub(r",\s*( finely\s+)?chopped.*$", "", remainder, flags=re.I)
    remainder = re.sub(r",\s*(diced|sliced|minced|grated|shredded|softened|melted|packed|rinsed|drained|peeled|trimmed|cut into[^,]*|room temperature).*$", "", remainder, flags=re.I)
    remainder = re.sub(r"\b(chopped|diced|sliced|minced|grated|shredded)\b", "", remainder, flags=re.I)
    remainder = remainder.strip(" ,;-")

    return {
        "amount": amount,
        "unit": unit,
        "name": remainder or text,
        "raw": text,
    }


def recipe_row_to_dict(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "servings": row["servings"],
        "ingredients": json.loads(row["ingredients"]),
        "instructions": row["instructions"],
        "notes": row["notes"],
        "tags": row["tags"],
        "source_url": row["source_url"],
        "image": row["image"],
        "prep_time": row["prep_time"],
        "cook_time": row["cook_time"],
        "total_time": row["total_time"],
        "created_at": row["created_at"],
    }


def validate_recipe_payload(data, partial=False):
    errors = []
    if not partial or "title" in data:
        if not str(data.get("title", "")).strip():
            errors.append("Title is required.")
    if not partial or "ingredients" in data:
        if not isinstance(data.get("ingredients"), list) or not data.get("ingredients"):
            errors.append("At least one ingredient line is required.")
    return errors


@app.get("/api/recipes")
def list_recipes():
    rows = get_db().execute("SELECT * FROM recipes ORDER BY title COLLATE NOCASE").fetchall()
    recipes = [recipe_row_to_dict(r) for r in rows]
    q = request.args.get("q", "").strip().lower()
    if q:
        recipes = [
            r for r in recipes
            if q in r["title"].lower()
            or q in r["tags"].lower()
            or any(q in ing.lower() for ing in r["ingredients"])
        ]
    return jsonify(recipes)


@app.get("/api/recipes/<int:recipe_id>")
def get_recipe(recipe_id):
    row = get_db().execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Recipe not found."}), 404
    return jsonify(recipe_row_to_dict(row))


@app.post("/api/recipes")
def create_recipe():
    data = request.get_json(force=True)
    errors = validate_recipe_payload(data)
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400
    db = get_db()
    cur = db.execute(
        "INSERT INTO recipes (title, servings, ingredients, instructions, notes, tags, source_url, image, prep_time, cook_time, total_time) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(data["title"]).strip(),
            int(data.get("servings") or 4),
            json.dumps([str(i).strip() for i in data["ingredients"] if str(i).strip()]),
            str(data.get("instructions", "") or ""),
            str(data.get("notes", "") or ""),
            str(data.get("tags", "") or ""),
            str(data.get("source_url", "") or ""),
            str(data.get("image", "") or ""),
            str(data.get("prep_time", "") or ""),
            str(data.get("cook_time", "") or ""),
            str(data.get("total_time", "") or ""),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM recipes WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(recipe_row_to_dict(row)), 201


@app.put("/api/recipes/<int:recipe_id>")
def update_recipe(recipe_id):
    db = get_db()
    row = db.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Recipe not found."}), 404
    data = request.get_json(force=True)
    errors = validate_recipe_payload(data, partial=True)
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400
    merged = {key: data.get(key, recipe_row_to_dict(row)[key]) for key in
              ("title", "servings", "ingredients", "instructions", "notes", "tags",
               "source_url", "image", "prep_time", "cook_time", "total_time")}
    if isinstance(merged["ingredients"], list):
        merged["ingredients"] = json.dumps([str(i).strip() for i in merged["ingredients"] if str(i).strip()])
    db.execute(
        "UPDATE recipes SET title=?, servings=?, ingredients=?, instructions=?, notes=?, tags=?, source_url=?, image=?, prep_time=?, cook_time=?, total_time=? WHERE id=?",
        (
            str(merged["title"]).strip(),
            int(merged["servings"] or 4),
            merged["ingredients"],
            str(merged["instructions"] or ""),
            str(merged["notes"] or ""),
            str(merged["tags"] or ""),
            str(merged["source_url"] or ""),
            str(merged["image"] or ""),
            str(merged["prep_time"] or ""),
            str(merged["cook_time"] or ""),
            str(merged["total_time"] or ""),
            recipe_id,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    return jsonify(recipe_row_to_dict(row))


@app.delete("/api/recipes/<int:recipe_id>")
def delete_recipe(recipe_id):
    db = get_db()
    db.execute("DELETE FROM meal_plan WHERE recipe_id = ?", (recipe_id,))
    cur = db.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "Recipe not found."}), 404
    return jsonify({"ok": True})


@app.post("/api/import")
def import_recipe():
    data = request.get_json(force=True)
    url = str(data.get("url", "")).strip()
    if not url or not re.match(r"^https?://", url):
        return jsonify({"error": "Please enter a valid http(s) recipe URL."}), 400
    try:
        recipe = fetch_recipe(url)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    saved = _insert_recipe(recipe)
    return jsonify(saved), 201


def _insert_recipe(parsed):
    db = get_db()
    cur = db.execute(
        "INSERT INTO recipes (title, servings, ingredients, instructions, source_url, image, prep_time, cook_time, total_time) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            parsed["title"],
            int(parsed.get("servings") or 4),
            json.dumps(parsed["ingredients"]),
            parsed.get("instructions", ""),
            parsed.get("source_url", ""),
            parsed.get("image", ""),
            parsed.get("prep_time", ""),
            parsed.get("cook_time", ""),
            parsed.get("total_time", ""),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM recipes WHERE id = ?", (cur.lastrowid,)).fetchone()
    return recipe_row_to_dict(row)


@app.get("/api/suggestions")
def list_suggestions():
    gf = request.args.get("gf") == "1"
    no_beef = request.args.get("no_beef") == "1"
    low_nightshade = request.args.get("low_nightshade") == "1"
    complete = request.args.get("complete") == "1"
    equipment = request.args.get("equipment", "")
    hidden = {r["title"] for r in get_db().execute("SELECT title FROM hidden_suggestions")}
    results = []
    for s in SUGGESTIONS:
        has_beef = bool(s.get("beef"))
        if s["title"] in hidden:
            continue
        if gf and s.get("gf") is False:
            continue
        if no_beef and has_beef and not s.get("beef_swap"):
            continue
        if low_nightshade and s.get("nightshade") == "heavy":
            continue
        if complete and not s.get("complete"):
            continue
        eq = set(s.get("equipment", []))
        if equipment == "oven" and "oven" not in eq:
            continue
        if equipment == "stovetop" and not eq & {"skillet", "pot"}:
            continue
        if equipment == "instantpot" and "instant pot" not in eq:
            continue
        if equipment == "sousvide" and "sous vide" not in eq:
            continue
        perfect = True
        if gf and s.get("gf") is not True:
            perfect = False
        if no_beef and has_beef:
            perfect = False
        if low_nightshade and s.get("nightshade") != "none":
            perfect = False
        out = dict(s)
        out["perfect"] = perfect
        results.append(out)
    results.sort(key=lambda r: (not r["perfect"], not r.get("complete")))
    return jsonify(results)


@app.post("/api/suggestions/hide")
def hide_suggestion():
    data = request.get_json(force=True)
    title = str(data.get("title", "")).strip()
    if not title:
        return jsonify({"error": "Title is required."}), 400
    db = get_db()
    db.execute("INSERT OR IGNORE INTO hidden_suggestions (title) VALUES (?)", (title,))
    db.commit()
    return jsonify({"ok": True})


@app.post("/api/suggestions/unhide")
def unhide_suggestion():
    data = request.get_json(force=True)
    title = str(data.get("title", "")).strip()
    if not title:
        return jsonify({"error": "Title is required."}), 400
    db = get_db()
    db.execute("DELETE FROM hidden_suggestions WHERE title = ?", (title,))
    db.commit()
    return jsonify({"ok": True})


@app.get("/api/suggestions/hidden")
def hidden_suggestions():
    rows = get_db().execute(
        "SELECT title FROM hidden_suggestions ORDER BY title COLLATE NOCASE"
    ).fetchall()
    return jsonify([r["title"] for r in rows])


@app.get("/api/plan")
def get_plan():
    week_start = _week_start(request.args.get("week"))
    days = []
    db = get_db()
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        rows = db.execute(
            "SELECT mp.id AS plan_id, mp.servings, r.* FROM meal_plan mp "
            "JOIN recipes r ON r.id = mp.recipe_id WHERE mp.plan_date = ? "
            "ORDER BY mp.id",
            (day.isoformat(),),
        ).fetchall()
        days.append({
            "date": day.isoformat(),
            "entries": [
                {
                    "plan_id": r["plan_id"],
                    "recipe_id": r["id"],
                    "title": r["title"],
                    "servings": r["servings"],
                    "planned_servings": r["servings"],
                }
                for r in rows
            ],
        })
    return jsonify({"week_start": week_start.isoformat(), "days": days})


@app.post("/api/plan")
def add_to_plan():
    data = request.get_json(force=True)
    try:
        plan_date = datetime.strptime(str(data.get("date", "")), "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date."}), 400
    recipe_id = int(data.get("recipe_id") or 0)
    servings = int(data.get("servings") or 0)
    db = get_db()
    recipe = db.execute("SELECT id, servings FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if recipe is None:
        return jsonify({"error": "Recipe not found."}), 404
    if not servings:
        servings = recipe["servings"]
    db.execute(
        "INSERT INTO meal_plan (plan_date, recipe_id, servings) VALUES (?, ?, ?) "
        "ON CONFLICT(plan_date, recipe_id) DO UPDATE SET servings = excluded.servings",
        (plan_date.isoformat(), recipe_id, servings),
    )
    db.commit()
    return jsonify({"ok": True}), 201


@app.delete("/api/plan/<int:plan_id>")
def remove_from_plan(plan_id):
    db = get_db()
    cur = db.execute("DELETE FROM meal_plan WHERE id = ?", (plan_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "Plan entry not found."}), 404
    return jsonify({"ok": True})


def _week_start(value):
    if value:
        try:
            d = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            d = date.today()
    else:
        d = date.today()
    return d - timedelta(days=d.weekday())


def _accumulate(entry, amount, unit, scale):
    family = unit_family(unit)
    if family:
        fam = entry.setdefault("families", {}).setdefault(
            family, {"base": 0.0, "seen": {}}
        )
        if unit not in fam["seen"]:
            fam["seen"][unit] = UNIT_FAMILIES[family][unit]
        fam["base"] += amount * scale * UNIT_FAMILIES[family][unit]
        entry["has_amount"] = True
    else:
        key = f"unit:{unit}"
        bucket = entry.setdefault("counts", {})
        bucket[key] = bucket.get(key, 0.0) + (amount or 1) * scale
        entry["has_amount"] = True


def _render_entry(entry):
    results = []
    for family, fam in sorted(entry.get("families", {}).items()):
        unit = best_display_unit(family, fam["base"], fam["seen"])
        display = fam["base"] / UNIT_FAMILIES[family][unit]
        results.append((format_amount(display), unit))
    for unit, total in sorted(entry.get("counts", {}).items()):
        unit = unit[5:]
        results.append((format_amount(total), unit))
    if not results:
        return "", ""
    qty, unit = results[0]
    if len(results) > 1:
        extras = ", ".join(f"{q} {u}".strip() for q, u in results[1:])
        qty = f"{qty} + {extras}" if extras else qty
    return qty, unit


def build_list_from_plan():
    merged = {}
    db = get_db()
    rows = db.execute(
        "SELECT mp.servings AS planned_servings, r.servings AS base_servings, r.ingredients "
        "FROM meal_plan mp JOIN recipes r ON r.id = mp.recipe_id"
    ).fetchall()
    for row in rows:
        scale = (row["planned_servings"] or row["base_servings"] or 4) / (row["base_servings"] or 4)
        for line in json.loads(row["ingredients"]):
            parsed = parse_ingredient_line(line)
            name = merge_ingredient_name(parsed["name"])
            if not name:
                continue
            entry = merged.setdefault(name, {"has_amount": False, "qty": "", "unit": ""})
            if parsed["amount"] is not None and row["base_servings"]:
                _accumulate(entry, parsed["amount"], parsed["unit"], scale)
                entry["qty"], entry["unit"] = _render_entry(entry)
            elif not entry["has_amount"]:
                entry["qty"], entry["unit"] = "", ""
    return merged


@app.post("/api/list/build")
def build_shopping_list():
    merged = build_list_from_plan()
    db = get_db()
    existing = {
        r["name"]: r for r in
        db.execute("SELECT * FROM shopping_items").fetchall()
    }
    added, updated = 0, 0
    for name, data in merged.items():
        qty, unit = data["qty"], data["unit"]
        category = guess_category(name, unit)
        current = existing.get(name)
        if current is None:
            db.execute(
                "INSERT INTO shopping_items (name, qty, unit, amount, category, source) VALUES (?, ?, ?, ?, ?, 'plan')",
                (name, qty, unit, None, category),
            )
            added += 1
        elif current["source"] == "plan":
            if not current["checked"]:
                db.execute(
                    "UPDATE shopping_items SET qty=?, unit=?, category=? WHERE id=?",
                    (qty, unit, category, current["id"]),
                )
            updated += 1
    db.commit()
    return jsonify({"ok": True, "added": added, "updated": updated})


@app.get("/api/list")
def get_shopping_list():
    rows = get_db().execute(
        "SELECT * FROM shopping_items ORDER BY checked ASC, "
        "CASE WHEN category='Produce' THEN 0 WHEN category='Meat & Seafood' THEN 1 "
        "WHEN category='Dairy & Eggs' THEN 2 WHEN category='Bakery' THEN 3 "
        "WHEN category='Pantry & Dry Goods' THEN 4 WHEN category='Spices & Seasonings' THEN 5 "
        "WHEN category='Frozen' THEN 6 WHEN category='Beverages' THEN 7 ELSE 9 END, "
        "name COLLATE NOCASE"
    ).fetchall()
    grouped = {}
    for r in rows:
        grouped.setdefault(r["category"], []).append({
            "id": r["id"], "name": r["name"], "qty": r["qty"], "unit": r["unit"],
            "checked": bool(r["checked"]), "source": r["source"],
        })
    return jsonify(grouped)


@app.post("/api/list")
def add_custom_item():
    data = request.get_json(force=True)
    raw = str(data.get("name", "")).strip()
    if not raw:
        return jsonify({"error": "Item name is required."}), 400
    parsed = parse_quantity(raw)
    if parsed.amount is not None and parsed.rest:
        name = merge_ingredient_name(parsed.rest)
        qty_text = f"{format_amount(parsed.amount)}".strip()
        unit = parsed.unit
    else:
        name = merge_ingredient_name(raw)
        qty_text = ""
        unit = ""
    category = str(data.get("category", "")).strip() or guess_category(name, unit)
    db = get_db()
    existing = db.execute(
        "SELECT * FROM shopping_items WHERE name = ? AND unit = ?",
        (name, unit),
    ).fetchone()
    if existing is None:
        existing = db.execute(
            "SELECT * FROM shopping_items WHERE name = ? AND (unit = '' OR (unit != '' AND ? != '')) LIMIT 1",
            (name, unit),
        ).fetchone()
    if existing and existing["checked"]:
        db.execute(
            "UPDATE shopping_items SET checked=0, qty=?, unit=?, category=? WHERE id=?",
            (qty_text or existing["qty"], unit or existing["unit"], category, existing["id"]),
        )
        db.commit()
        return jsonify({"ok": True, "unarchived": True}), 200
    db.execute(
        "INSERT INTO shopping_items (name, qty, unit, amount, category, source) VALUES (?, ?, ?, ?, ?, 'custom') "
        "ON CONFLICT(name, unit) DO UPDATE SET qty=excluded.qty, checked=0, category=excluded.category",
        (name, qty_text, unit, None, category),
    )
    db.commit()
    return jsonify({"ok": True}), 201


@app.patch("/api/list/<int:item_id>")
def toggle_item(item_id):
    db = get_db()
    row = db.execute("SELECT checked FROM shopping_items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Item not found."}), 404
    db.execute("UPDATE shopping_items SET checked = ? WHERE id = ?", (0 if row["checked"] else 1, item_id))
    db.commit()
    return jsonify({"ok": True, "checked": not bool(row["checked"])})


@app.delete("/api/list/<int:item_id>")
def delete_item(item_id):
    db = get_db()
    cur = db.execute("DELETE FROM shopping_items WHERE id = ?", (item_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "Item not found."}), 404
    return jsonify({"ok": True})


@app.post("/api/list/clear-checked")
def clear_checked():
    db = get_db()
    cur = db.execute("DELETE FROM shopping_items WHERE checked = 1")
    db.commit()
    return jsonify({"ok": True, "removed": cur.rowcount})


if __name__ == "__main__":
    host = os.environ.get("MEALPLANNER_HOST", "127.0.0.1")
    print("\n  Family Meal Planner")
    print(f"  Open http://127.0.0.1:5000 on this computer.")
    if host == "127.0.0.1":
        print("  To open it from your phones on the same Wi-Fi, start it with:")
        print("    MEALPLANNER_HOST=0.0.0.0 python app.py")
        print("  (then visit http://<this-computer's-IP>:5000 from a phone)\n")
    app.run(host=host, port=5000, debug=False)
