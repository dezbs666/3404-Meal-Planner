"""Schema.org recipe parsing: JSON-LD first, then HTML microdata fallback."""
import json
import re
from html.parser import HTMLParser

RECIPE_TYPE = {"recipe", "http://schema.org/recipe", "https://schema.org/recipe"}


def _as_list(value):
    if isinstance(value, list):
        return value
    return [value]


def _clean_text(value):
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text


def _extract_from_jsonld(data):
    if isinstance(data, list):
        for item in data:
            found = _extract_from_jsonld(item)
            if found:
                return found
        return None
    if not isinstance(data, dict):
        return None
    ctx = data.get("@context")
    types = _as_list(data.get("@type", []))
    types = [str(t).lower() for t in types]
    if (ctx in ("http://schema.org", "https://schema.org", None) and "recipe" in types):
        return data
    for key in ("@graph",):
        if key in data:
            found = _extract_from_jsonld(data[key])
            if found:
                return found
    return None


class _MicrodataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.recipe = None
        self._stack = []
        self._recipe_depth = None
        self._current_prop = None
        self._prop_depth = None
        self._buffer = []
        self._props = {}

    def handle_starttag(self, tag, attrs):
        amap = dict(attrs)
        itemscope = "itemscope" in amap
        itemtype = (amap.get("itemtype") or "").rstrip("/").lower()
        is_recipe = itemscope and itemtype.endswith("schema.org/recipe")
        self._stack.append({"is_recipe": is_recipe, "prop": amap.get("itemprop")})
        if is_recipe and self._recipe_depth is None:
            self._recipe_depth = len(self._stack)
            self._props = {}
        elif self._recipe_depth is not None and self._current_prop is None:
            prop = amap.get("itemprop")
            if prop:
                self._current_prop = prop
                self._prop_depth = len(self._stack)
                self._buffer = []
                if tag == "meta":
                    self._props.setdefault(prop, []).append(_clean_text(amap.get("content", "")))
                    self._current_prop = None
                    self._prop_depth = None

    def handle_endtag(self, tag):
        if self._stack:
            self._stack.pop()
        if self._current_prop is not None and len(self._stack) < self._prop_depth:
            text = _clean_text("".join(self._buffer))
            if text:
                self._props.setdefault(self._current_prop, []).append(text)
            self._current_prop = None
            self._prop_depth = None
        if self._recipe_depth is not None and len(self._stack) < self._recipe_depth:
            self._recipe_depth = None

    def handle_data(self, data):
        if self._current_prop is not None:
            self._buffer.append(data)


def extract_recipe(html, base_url=""):
    recipe = None
    for match in re.finditer(
        r'<script[^>]*type=["\']?application/ld\+json["\']?[^>]*>(.*?)</script>',
        html, re.S | re.I,
    ):
        raw = match.group(1).strip().replace("\x00", "")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        recipe = _extract_from_jsonld(data)
        if recipe:
            break
    if recipe is None:
        parser = _MicrodataParser()
        try:
            parser.feed(html)
        except Exception:
            pass
        if parser._props and "name" in parser._props:
            recipe = parser._props
    if not recipe:
        return None
    return normalize_recipe(recipe, base_url)


def normalize_recipe(raw, base_url=""):
    def first(key):
        values = _as_list(raw.get(key, ""))
        for value in values:
            text = _clean_text(value)
            if text:
                return text
        return ""

    title = first("name")
    if not title:
        return None

    servings_text = first("recipeYield") or first("yield")
    servings = parse_servings(servings_text)

    ingredients = []
    for item in _as_list(raw.get("recipeIngredient", raw.get("ingredients", []))):
        text = _clean_text(item)
        if text:
            ingredients.append(text)
    if not ingredients:
        for item in _as_list(raw.get("recipeInstructions", [])):
            if isinstance(item, dict):
                text = _clean_text(item.get("text", ""))
            else:
                text = _clean_text(item)
            if text:
                ingredients.append(text)

    instructions = []
    raw_instructions = raw.get("recipeInstructions", [])
    if isinstance(raw_instructions, dict):
        raw_instructions = [raw_instructions]
    for item in raw_instructions:
        if isinstance(item, dict):
            text = _clean_text(item.get("text", ""))
        else:
            text = _clean_text(item)
        if text and text not in instructions:
            instructions.append(text)
    if not instructions:
        howto = first("recipeInstructions")
        if howto:
            instructions = [line for line in howto.split("\n") if line.strip()]

    image = ""
    images = _as_list(raw.get("image", []))
    for img in images:
        if isinstance(img, dict):
            img = img.get("url", "")
        img = _clean_text(img)
        if img:
            if img.startswith("//"):
                img = "https:" + img
            elif img.startswith("/") and base_url:
                from urllib.parse import urljoin
                img = urljoin(base_url, img)
            image = img
            break

    times = {}
    for key in ("prepTime", "cookTime", "totalTime"):
        value = first(key)
        if value:
            times[key] = _iso_duration_to_text(value)

    return {
        "title": title,
        "servings": servings,
        "ingredients": ingredients,
        "instructions": "\n".join(instructions),
        "image": image,
        "source_url": base_url,
        "prep_time": times.get("prepTime", ""),
        "cook_time": times.get("cookTime", ""),
        "total_time": times.get("totalTime", ""),
    }


def parse_servings(text):
    if not text:
        return 4
    if isinstance(text, (int, float)):
        return max(1, int(text))
    numbers = re.findall(r"\d+(?:\.\d+)?", str(text))
    if not numbers:
        return 4
    return max(1, int(float(numbers[-1])))


def _iso_duration_to_text(value):
    value = str(value)
    match = re.match(r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", value)
    if not match or not any(match.groups()):
        return value if not value.startswith("P") else ""
    days, hours, minutes = (int(g) if g else 0 for g in match.groups())
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    return " ".join(parts)


def fetch_recipe(url):
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError

    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
    })
    try:
        with urlopen(req, timeout=15) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            html = resp.read(2_000_000).decode(charset, errors="replace")
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise ValueError(f"Could not fetch {url}: {exc}") from exc
    recipe = extract_recipe(html, base_url=url)
    if not recipe:
        raise ValueError(
            "No structured recipe found on that page. "
            "Not every site publishes recipe data the importer can read; "
            "try another link or add the recipe manually."
        )
    return recipe
