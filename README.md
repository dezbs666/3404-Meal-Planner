# Family Meal Planner

A small, self-hosted meal-planning web app for two people: bring your own
recipes, plan the week, and generate a combined shopping list — no account,
no subscription, no company that can shut it down.

## Features

- **Import recipes from webpages** — paste a URL from any recipe site that
  publishes structured recipe data (most major sites do). The importer reads
  schema.org JSON-LD and HTML microdata.
- **Add your own recipes** — simple form: title, servings, ingredients one per
  line (`2 cups cooked rice`, `1/2 onion, diced`), instructions, tags.
- **Weekly meal planner** — assign recipes to days of the week (Monday-start),
  move between weeks, set servings per planned meal.
- **Shopping list** — one tap builds a combined list from everything in your
  plan. Identical ingredients merge and quantities scale to planned servings
  (`1½ cups` + `2 cups` → `3½ cups`). Items are grouped by store section
  (produce, meat, dairy…). Add any other grocery items yourself, check things
  off as you shop, or clear the list and start over.

## Running it

Requires Python 3.9+.

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5000** in a browser.

### Using it from your phones

Run it on a computer that stays on (laptop, desktop, NAS, Raspberry Pi) and
start it with:

```bash
MEALPLANNER_HOST=0.0.0.0 python app.py
```

Then on each phone, open `http://<computer's-IP>:5000` in the browser
(find the computer's IP with `ipconfig` on Windows or `ifconfig`/`ip addr` on
macOS/Linux). Tip the page to your phones' home screens and it behaves like an
app. Both of you see and edit the same list.

On Windows, use `set MEALPLANNER_HOST=0.0.0.0` before `python app.py`.

### Keeping the data

Everything lives in one SQLite file, `mealplanner.db`, next to `app.py`.
Copy that file somewhere safe (or into a synced folder) and you have a backup.
To start fresh, just delete it.

## Notes

- The web importer understands most sites but not all of them — if a site
  doesn't work, it will say so; add that recipe manually instead.
- First, only signed-in members can edit — there's no login; the app assumes
  it runs inside your home network. Don't port-forward it to the internet.

## Project layout

```
app.py            Flask server + REST API + SQLite
recipe_import.py  schema.org JSON-LD / microdata recipe parsing
quantities.py     quantity parsing, unit normalization, aisle categories
templates/        single-page UI
static/           styles + frontend JS
```
