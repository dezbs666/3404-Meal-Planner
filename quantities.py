"""Quantity parsing and unit normalization for merging shopping-list ingredients."""
import re

FRACTIONS = {
    "¼": 0.25, "½": 0.5, "¾": 0.75, "⅓": 1/3, "⅔": 2/3,
    "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875, "⅕": 0.2, "⅖": 0.4,
}

UNIT_ALIASES = {
    "g": "gram", "gr": "gram", "gram": "gram", "grams": "gram", "gramme": "gram",
    "kg": "kilogram", "kgs": "kilogram", "kilogram": "kilogram", "kilograms": "kilogram", "kilo": "kilogram",
    "mg": "milligram", "milligram": "milligram", "milligrams": "milligram",
    "lb": "pound", "lbs": "pound", "lb.": "pound", "pound": "pound", "pounds": "pound", "lb s": "pound",
    "oz": "ounce", "oz.": "ounce", "ounce": "ounce", "ounces": "ounce",
    "ml": "milliliter", "milliliter": "milliliter", "millilitre": "milliliter", "milliliters": "milliliter", "millilitres": "milliliter", "cc": "milliliter",
    "l": "liter", "ltr": "liter", "liter": "liter", "litre": "liter", "liters": "liter", "litres": "liter",
    "tsp": "teaspoon", "tsp.": "teaspoon", "tsps": "teaspoon", "teaspoon": "teaspoon", "teaspoons": "teaspoon",
    "tbsp": "tablespoon", "tbsp.": "tablespoon", "tbs": "tablespoon", "tbsps": "tablespoon", "tablespoon": "tablespoon", "tablespoons": "tablespoon", "tbl": "tablespoon",
    "cup": "cup", "cups": "cup", "c": "cup",
    "qt": "quart", "quart": "quart", "quarts": "quart",
    "pt": "pint", "pint": "pint", "pints": "pint",
    "fl oz": "fluid ounce", "fluid ounce": "fluid ounce", "fluid ounces": "fluid ounce", "floz": "fluid ounce",
    "clove": "clove", "cloves": "clove",
    "pinch": "pinch", "pinches": "pinch", "dash": "pinch",
    "sprig": "sprig", "sprigs": "sprig",
    "can": "can", "cans": "can",
    "slice": "slice", "slices": "slice",
    "stalk": "stalk", "stalks": "stalk",
    "leaf": "leaf", "leaves": "leaf",
    "bunch": "bunch", "bunches": "bunch",
    "head": "head", "heads": "head",
    "package": "package", "pack": "package", "packets": "package", "packet": "package",
    "piece": "piece", "pieces": "piece",
    "stick": "stick", "sticks": "stick",
    "spring": "spring", "springs": "spring",
    "": "",
}


class ParsedQuantity:
    __slots__ = ("amount", "unit", "rest")

    def __init__(self, amount, unit, rest):
        self.amount = amount
        self.unit = unit
        self.rest = rest


def normalize_unit(unit):
    unit = unit.strip().lower().rstrip(".")
    return UNIT_ALIASES.get(unit, unit)


def parse_quantity(text):
    text = text.strip()
    text = text.replace("½", " 1/2 ").replace("¼", " 1/4 ").replace("¾", " 3/4 ")
    text = text.replace("⅓", " 1/3 ").replace("⅔", " 2/3 ").replace("⅛", " 1/8 ")
    for sym, val in FRACTIONS.items():
        text = text.replace(sym, f" {val} ")
    text = text.strip()

    match = re.match(r"^(\d+)\s+(\d+)\s*/\s*(\d+)(.*)$", text)
    if match:
        whole, num, den, rest = match.groups()
        amount = int(whole) + int(num) / int(den)
        return ParsedQuantity(amount, "", rest.strip())

    match = re.match(r"^(\d+)\s*/\s*(\d+)(.*)$", text)
    if match:
        num, den, rest = match.groups()
        return ParsedQuantity(int(num) / int(den), "", rest.strip())

    match = re.match(r"^(\d+(?:\.\d+)?|\.\d+)\s*(.*)$", text)
    if match:
        amount = float(match.group(1))
        rest = match.group(2)
        unit_match = re.match(r"^([a-zA-Z][a-zA-Z. ]*?)\b\s*(.*)$", rest)
        unit, remainder = "", rest
        if unit_match:
            candidate = normalize_unit(unit_match.group(1))
            if candidate in UNIT_ALIASES.values():
                unit = candidate
                remainder = unit_match.group(2)
        return ParsedQuantity(amount, unit, remainder.strip())

    return ParsedQuantity(None, "", text)


def format_amount(amount):
    whole = int(amount)
    frac = amount - whole
    common = {0.25: "¼", 0.5: "½", 0.75: "¾", 1/3: "⅓", 2/3: "⅔", 0.125: "⅛", 0.875: "⅞", 0.375: "⅜"}
    for value, sym in common.items():
        if abs(frac - value) < 0.02:
            return f"{whole} {sym}".strip() if whole else sym
    if abs(frac) < 0.02:
        return str(whole)
    if abs(amount - round(amount, 2)) < 0.005:
        return f"{amount:g}"
    return f"{amount:.2f}".rstrip("0").rstrip(".")


def merge_ingredient_name(name):
    name = re.sub(r"\s+", " ", name.strip().lower())
    name = name.rstrip(".")
    return name


def guess_category(name, unit):
    text = f"{name} {unit}".lower()
    categories = [
        ("Produce", "onion garlic pepper tomato lettuce spinach kale carrot celery potato sweet potato broccoli "
         "cauliflower zucchini cucumber mushroom avocado lemon lime orange apple banana berry berries strawberry "
         "cilantro parsley basil mint thyme rosemary ginger scallion green onion shallot cabbage corn squash "
         "eggplant asparagus pea beans green bean fruit salad greens arugula radish beet"),
        ("Meat & Seafood", "chicken beef pork turkey sausage bacon ham steak ground lamb shrimp salmon fish tilapia "
         "cod tuna scallop crab lobster thigh breast drumstick rib roast chuck sirloin brisket chorizo prosciutto "
         "pancetta hot dog meatball"),
        ("Dairy & Eggs", "milk cream butter yogurt yoghurt cheese cheddar mozzarella parmesan feta ricotta mascarpone "
         "cream cheese sour cream half-and-half egg eggs egg white yolk heavy whipping buttermilk ghee"),
        ("Bakery", "bread bun buns roll rolls bagel tortilla pita naan croissant baguette english muffin crouton "
         "breadcrumb crumb wrapper wrapper tortillas"),
        ("Pantry & Dry Goods", "flour sugar rice pasta noodle spaghetti penne macaroni lentil chickpea bean quinoa oat "
         "oil olive vegetable canola sesame salt pepper stock broth bouillon vinegar salsa sauce ketchup mustard "
         "mayo mayonnaise honey maple syrup vanilla baking soda powder yeast chocolate chip cocoa peanut butter "
         "jam jelly canned tomato paste curry coconut milk breadcrumb tortilla chip cracker cereal trail mix nut "
         "almond walnut cashew peanut pecan raisin dried apricot tuna canned corn pickle olive"),
        ("Spices & Seasonings", "cumin paprika oregano chili powder cayenne turmeric cinnamon nutmeg cardamom coriander "
         "bay leaf leaves allspice cloves ginger powder garlic powder onion powder italian seasoning za'atar "
         "garam masala curry powder italian herb red pepper flakes"),
        ("Frozen", "frozen ice cream peas peas-and-carrots edamame waffle ice popsicle"),
        ("Beverages", "juice water soda beer wine coffee tea sparkling cider cranberry"),
        ("Other", ""),
    ]
    for category, keywords in categories[:-1]:
        for keyword in keywords.split():
            if re.search(rf"\b{re.escape(keyword)}", text):
                return category
    return "Other"


_ORDER = ["Produce", "Meat & Seafood", "Dairy & Eggs", "Bakery", "Pantry & Dry Goods",
          "Spices & Seasonings", "Frozen", "Beverages", "Other"]

UNIT_FAMILIES = {
    "volume": {"teaspoon": 5, "tablespoon": 15, "fluid ounce": 30, "cup": 240,
               "pint": 473, "quart": 946, "liter": 1000, "milliliter": 1},
    "weight": {"gram": 1, "kilogram": 1000, "ounce": 28.35, "pound": 453.592},
}


def unit_family(unit):
    for family, units in UNIT_FAMILIES.items():
        if unit in units:
            return family
    return None


def convert(amount, from_unit, to_unit):
    for units in UNIT_FAMILIES.values():
        if from_unit in units and to_unit in units:
            return amount * units[from_unit] / units[to_unit]
    return None


def best_display_unit(family, base_total, units_seen):
    units = UNIT_FAMILIES[family]
    known = set(units_seen)
    for unit in sorted(units, key=units.get, reverse=True):
        if unit in known and base_total / units[unit] >= 0.5:
            return unit
    for unit in sorted(units, key=units.get, reverse=True):
        if unit in known:
            return unit
    if family == "volume":
        return "cup" if base_total / units["cup"] >= 0.5 else "tablespoon"
    return "pound" if base_total / units["pound"] >= 0.5 else "ounce"


def category_sort_key(category):
    try:
        return _ORDER.index(category)
    except ValueError:
        return len(_ORDER)
