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
- **Recipe ideas** — a built-in set of simple, family-tested suggestions with
  filters for gluten-free, no beef, "easy on nightshades & potatoes" (and
  never Brussels sprouts!), plus a **complete meals with veggies** preference.
  Filter by the equipment you own — oven, stovetop, Instant Pot, sous vide.
  The lineup refreshes itself every week, and *New ideas* shuffles up a new
  batch any time. Recipes that need a tweak come with a swap note (e.g. "use
  tamari instead of soy sauce"), anything you're not interested in can be
  hidden with one tap, and *Hidden ideas* brings it back later.

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

### Installing on a Raspberry Pi (Linux)

From a PC that can reach the Pi (e.g. over Tailscale SSH), spot it on, clone
the repo, and run the installer once — the app then runs as a service and
starts automatically at boot:

```bash
ssh <user>@<pi-address>
git clone https://github.com/dezbs666/3404-Meal-Planner.git
cd 3404-Meal-Planner
sudo bash install.sh
```

The installer creates a virtual environment, installs dependencies, and sets
up the systemd service, then prints the address to open
(`http://<pi-ip>:5000` — from any device on your tailnet or home network).

### Keeping the data

Everything lives in one SQLite file, `mealplanner.db`, next to `app.py`.
Copy that file somewhere safe (or into a synced folder) and you have a backup.
To start fresh, just delete it.

## Notes

- The web importer understands most sites but not all of them — if a site
  doesn't work, it will say so; add that recipe manually instead.
- There's no login by design — the app assumes it runs inside your home
  network. Don't port-forward it to the internet.

## Project layout

```
app.py            Flask server + REST API + SQLite
recipe_import.py  schema.org JSON-LD / microdata recipe parsing
suggestions.py    curated recipe ideas + dietary/equipment metadata
quantities.py     quantity parsing, unit normalization, aisle categories
templates/        single-page UI
static/           styles + frontend JS
```
