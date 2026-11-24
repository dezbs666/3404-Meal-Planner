"""Web recipe suggestions from TheMealDB (https://www.themealdb.com).

TheMealDB's public API needs no key, so this works on a self-hosted box with
plain stdlib. Random meals are fetched in parallel, run through a keyword
classifier for the household's restrictions (gluten, beef, nightshades &
potatoes, Brussels sprouts), and returned in the same shape as the presets in
suggestions.py so the frontend treats them identically.

Keyword checks are a best effort — the UI says to double-check labels.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen

MEALDB_RANDOM = "https://www.themealdb.com/api/json/v1/1/random.php"

GLUTEN_HARD = (
    "wheat", "flour", "breadcrumb", "bread crumb", "breadcrumbs", "bread",
    "bun", "pasta", "spaghetti", "macaroni", "lasag", "noodle", "tortilla",
    "panko", "semolina", "couscous", "barley", "rye", "seitan", "biscuit",
    "cracker", "graham", "dough", "gnocchi", "beer", "crust", "dumpling",
    "naan", "croissant", "baguette", "puff pastry", "pie",
)

NIGHTSHADE_PATTERNS = (
    r"tomato", r"tomatillo", r"salsa", r"ketchup", r"\bchil[ei]\b",
    r"jalape", r"chipotle", r"habanero", r"sriracha", r"tabasco", r"harissa",
    r"gochujang", r"enchilada", r"paprika", r"cayenne", r"red pepper",
    r"crushed pepper", r"pepper flakes", r"\bbell pepper", r"\bpeppers?\b",
    r"eggplant", r"aubergine", r"potato", r"potatoes",
)

VEG_PATTERNS = (
    r"broccoli", r"spinach", r"kale", r"cabbage", r"lettuce", r"salad",
    r"carrot", r"parsnip", r"turnip", r"\bpeas\b", r"mangetout", r"edamame",
    r"green bean", r"asparagus", r"artichoke", r"zucchini", r"courgette",
    r"squash", r"cauliflower", r"celery", r"\bcorn\b", r"cucumber",
    r"beet", r"fennel", r"leek", r"mushroom", r"\bpeppers?\b", r"bamboo",
    r"bean sprouts", r"bok choy", r" pak choi", r"watercress", r"arugula",
    r"\bbeans\b", r"lentil",
)

BEEF_WORDS = ("beef", "steak", "sirloin", "ribeye", "brisket", "burger")
FISH_STEAKS = ("salmon", "tuna", "swordfish", "cod", "halibut",
               "sword fish", "mackerel")

EXEMPT_GLUETEN_FREE_PHRASES = (
    "corn tortilla", "rice noodle", "rice paper", "rice flour",
    "chickpea flour", "garbanzo flour", "almond flour", "coconut flour",
    "buckwheat flour", "corn flour", "masa", "ginger ale", "buckwheat",
)

NON_GF_SWAP = {"soy sauce": "swap soy sauce for tamari",
               "oat": "use certified gluten-free oats"}


def _join_ingredients(meal):
    lines = []
    for i in range(1, 21):
        ing = (meal.get(f"strIngredient{i}") or "").strip()
        if not ing:
            continue
        measure = (meal.get(f"strMeasure{i}") or "").strip()
        line = f"{measure} {ing}".strip()
        lines.append(line[0].upper() + line[1:] if line else ing)
    return lines


def _split_instructions(text):
    parts = re.split(r"\r?\n+|(?=STEP \d)", text or "")
    return [re.sub(r"^STEP \d+[:.]?\s*", "", p, flags=re.I).strip()
            for p in parts if p.strip()]


def _ns_match_count(lines):
    hits = set()
    for i, line in enumerate(lines):
        low = line.lower()
        low = re.sub(r"(black|white|lemon|peppercorn|cracked)\s+peppers?", " ", low)
        for pattern in NIGHTSHADE_PATTERNS:
            if re.search(pattern, low):
                hits.add((i, line))
                break
    return hits


def _classify(lines):
    text = " ".join(lines).lower()
    if re.search(r"brussels", text):
        return {"brussels": True}

    probe = text
    for phrase in EXEMPT_GLUETEN_FREE_PHRASES:
        probe = probe.replace(phrase, " ")

    gf_swaps = []
    for phrase, note in NON_GF_SWAP.items():
        if re.search(r"\b" + phrase, probe):
            gf_swaps.append(note)
            probe = probe.replace(phrase, " ")

    gf = not any(w in probe for w in GLUTEN_HARD)
    if not gf:
        gf = False
    elif gf_swaps:
        gf = "; ".join(gf_swaps) + " \u2014 the rest of the ingredients are gluten-free; double-check labels."

    steaks_in_fish = any(
        f" {f} " in f" {probe}" and re.search(r"\bsteak", probe)
        for f in FISH_STEAKS
    )
    probe_beef = probe
    if steaks_in_fish:
        probe_beef = re.sub(r"\bsteak\b", " ", probe_beef)
    for f in FISH_STEAKS:
        probe_beef = probe_beef.replace(f, " ")
    beef = any(re.search(r"\b" + w + r"\b", probe_beef) for w in BEEF_WORDS)

    ns_hits = _ns_match_count(lines)
    distinct = len({line for _, line in ns_hits})
    if distinct >= 2:
        nightshade = "heavy"
    elif distinct == 1:
        nightshade = "light"
    else:
        nightshade = "none"
    ns_note = None
    if ns_hits:
        names = sorted({line for _, line in ns_hits})[:3]
        ns_note = "Contains: " + ", ".join(names) + (
            " " if distinct < 2 else ""
        )

    complete = any(re.search(p, text) for p in VEG_PATTERNS)

    return {
        "brussels": False,
        "gf": gf,
        "beef": beef,
        "nightshade": nightshade,
        "ns_note": ns_note,
        "complete": complete,
    }


def _fetch_random():
    req = Request(MEALDB_RANDOM, headers={"User-Agent": "mealplanner/1.0"})
    with urlopen(req, timeout=8) as resp:
        data = json.load(resp)
    meals = data.get("meals") or []
    return meals[0] if meals else None


def _meal_to_suggestion(meal):
    lines = _join_ingredients(meal)
    if len(lines) < 3:
        return None
    info = _classify(lines)
    if info.get("brussels"):
        return None
    area = (meal.get("strArea") or "").strip()
    category = (meal.get("strCategory") or "").strip()
    tags = [t for t in (area, category) if t]
    meal_id = meal.get("idMeal") or ""
    return {
        "title": (meal.get("strMeal") or "").strip(),
        "servings": 4,
        "total_time": "",
        "equipment": [],
        "ingredients": lines,
        "instructions": _split_instructions(meal.get("strInstructions") or ""),
        "tags": tags,
        "gf": info["gf"],
        "beef": info["beef"],
        "nightshade": info["nightshade"],
        "ns_note": info["ns_note"],
        "complete": info["complete"],
        "source_url": f"https://www.themealdb.com/meal/{meal_id}" if meal_id else "",
        "image": meal.get("strMealThumb") or "",
        "web": True,
    }


def build_web_suggestions(gf, no_beef, low_nightshade, complete,
                          attempts=8, hidden_titles=(), saved_titles=()):
    try:
        with ThreadPoolExecutor(max_workers=attempts) as pool:
            futures = [pool.submit(_fetch_random) for _ in range(attempts)]
            meals = [f.result() for f in as_completed(futures)]
    except Exception:
        raise RuntimeError("mealdb unreachable")

    hidden = {t.lower() for t in hidden_titles}
    saved = {t.lower() for t in saved_titles}

    results = []
    seen = set()
    for meal in meals:
        if not meal:
            continue
        title = (meal.get("strMeal") or "").strip()
        key = title.lower()
        if not title or key in seen or key in hidden or key in saved:
            continue
        seen.add(key)
        s = _meal_to_suggestion(meal)
        if s is None:
            continue
        if gf and s["gf"] is False:
            continue
        if no_beef and s["beef"]:
            continue
        if low_nightshade and s["nightshade"] == "heavy":
            continue
        if complete and not s["complete"]:
            continue
        perfect = (
            (s["gf"] is True)
            and not s["beef"]
            and s["nightshade"] == "none"
            and (s["complete"] if complete else True)
        )
        s["perfect"] = perfect
        results.append(s)

    results.sort(key=lambda r: (not r["perfect"], not r["complete"]))
    return results
