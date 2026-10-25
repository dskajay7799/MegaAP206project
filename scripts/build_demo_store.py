"""Builds the Verity demo store: demo_store/catalogue.json + frontend/assets/products/*.svg (3 views per product).

Run:  python scripts/build_demo_store.py
Everything here is SYNTHETIC demonstration data: brands are fictional, prices/ratings/stock are made up, price history entries marked
`price_history` are simulated, and the images are generated illustrations (not photographs).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import product_art as art  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_IMG = ROOT / "frontend" / "assets" / "products"
OUT_DIR = ROOT / "demo_store"

HEX = {"Black": "#1c1c22", "Sand": "#d8c3a5", "Blue": "#2f4bff", "White": "#f3f3ef", "Sky Blue": "#8ec5ff", "Beige": "#d9c7a3", "Olive": "#6b7a3a", "Navy": "#1d2a5c",
       "Grey": "#8a8f9c", "Indigo": "#2c3e8c", "Charcoal": "#3a3d46", "Maroon": "#7b1e3a", "Silver": "#c4c8d2", "Brown": "#6b4226", "Teal": "#1b8a8a", "Green": "#2e9e6b",
       "Purple": "#6b4de6", "Coral": "#e8604c"}
TINT = {"Electronics": "#dfe4ff", "Fashion": "#f0e4d8", "Footwear": "#dff0e4", "Home & Kitchen": "#f6e8d2", "Beauty & Personal Care": "#f7dfe6",
        "Sports & Fitness": "#e0eefc", "Books & Stationery": "#ece4f8", "Bags": "#e4ecdd"}
S5, SH, SZ = ["S", "M", "L", "XL"], ["6", "7", "8", "9", "10"], ["28", "30", "32", "34", "36"]

PRODUCTS = []


def P(pid, title, brand, cat, sub, price, desc, kind, specs, use, rating, hl, *, colours=None, sizes=None, attrs=None, stock=None, per=6, accent="#c8f560",
      pal=None, featured=False, days=120, hist=None, out=False, oos=None):
    opts, attrs = {}, dict(attrs or {})
    if colours:
        if len(colours) > 1:
            opts["colour"] = colours                   # a real choice -> variants
        else:
            attrs.setdefault("colour", colours[0])     # a single colour is a fact, not an option
    if sizes:
        opts["size"] = sizes
    a = HEX[colours[0]] if colours else (pal or "#2540ff")
    rec = {"id": pid, "sku": pid.replace("VRT-", "VRT"), "title": title, "brand": brand, "category": cat, "subcategory": sub, "description": desc, "price": price,
           "rating": rating, "specs": specs, "use_cases": use, "highlights": hl, "featured": featured, "added_days_ago": days,
           "images": [f"/assets/products/{pid}-{i}.svg" for i in (1, 2, 3)]}
    if attrs:
        rec["attributes"] = attrs
    if opts:
        rec["options"] = opts
        rec["stock_per_variant"] = 0 if out else per
        if oos:
            rec["unavailable"] = oos
    else:
        rec["stock_qty"] = 0 if out else (stock if stock is not None else 15)
    if hist:
        rec["price_history"] = [{"days_ago": d, "price": p} for d, p in hist]
    PRODUCTS.append((rec, kind, {"a": a, "b": accent, "c": HEX.get(colours[1], "#f4b400") if colours and len(colours) > 1 else "#f4b400"}))


E, F, FT, H, B, SP, ST, BG = "Electronics", "Fashion", "Footwear", "Home & Kitchen", "Beauty & Personal Care", "Sports & Fitness", "Books & Stationery", "Bags"
# ------------------------------------------------------------------ Electronics
P("VRT-1001", "Halo ANC Wireless Headphones", "Halo Audio", E, "Headphones", 4999, "Over-ear Bluetooth headphones with active noise cancelling and a built-in microphone for calls.", "headphones",
  {"battery_hours": 40, "charge_time_min": 120, "weight_g": 265, "noise_cancellation": True, "bluetooth": "5.3", "driver_mm": 40, "microphone": True, "wireless": True}, ["study", "commute", "travel", "office"], 4.4,
  ["Active noise cancelling", "40-hour listed battery life", "Foldable ear cups"], colours=["Black", "Sand"], per=9, accent="#2540ff", featured=True, days=12, hist=[(90, 5499), (45, 5299)])
P("VRT-1002", "Pulse Lite Wireless Headphones", "Pulse", E, "Headphones", 2499, "Lightweight on-ear Bluetooth headphones for everyday listening. No noise cancelling.", "headphones",
  {"battery_hours": 30, "charge_time_min": 150, "weight_g": 220, "noise_cancellation": False, "bluetooth": "5.2", "driver_mm": 40, "microphone": True, "wireless": True}, ["study", "commute", "gym"], 4.1,
  ["30-hour listed battery life", "220 g", "Built-in microphone"], colours=["Black", "Blue"], per=12, accent="#c8f560", days=70, hist=[(100, 2799), (50, 2599)])
P("VRT-1003", "Tonic Studio Wired Headphones", "Tonic", E, "Headphones", 1499, "Wired over-ear headphones with a 3.5 mm cable. No battery to charge and no microphone.", "headphones_wired",
  {"weight_g": 240, "noise_cancellation": False, "microphone": False, "wireless": False}, ["study", "office", "home"], 4.0, ["Wired, nothing to charge", "Closed-back ear cups"],
  colours=["Black"], stock=18, accent="#e8604c", days=200)
P("VRT-1004", "Orbit True Wireless Earbuds", "Orbit", E, "Earbuds", 2999, "True wireless earbuds with noise cancelling and a pocket charging case.", "earbuds",
  {"battery_hours": 28, "charge_time_min": 90, "weight_g": 52, "noise_cancellation": True, "water_resistance": "IPX4", "bluetooth": "5.3", "microphone": True, "wireless": True}, ["commute", "gym", "travel"], 4.3,
  ["28 hours including the case", "IPX4 water resistance", "Active noise cancelling"], colours=["White", "Black"], per=10, accent="#2540ff", featured=True, days=25)
P("VRT-1005", "Nimbus Earbuds Mini", "Nimbus", E, "Earbuds", 1499, "Compact true wireless earbuds with a sweat-resistant build. Currently sold out in the demo store.", "earbuds",
  {"battery_hours": 20, "charge_time_min": 80, "weight_g": 40, "noise_cancellation": False, "water_resistance": "IPX5", "bluetooth": "5.1", "wireless": True}, ["gym", "commute"], 4.0,
  ["20 hours including the case", "IPX5 water resistance"], colours=["Black"], out=True, accent="#e8604c", days=160)
P("VRT-1006", "Cube Bluetooth Speaker", "Cube Labs", E, "Speakers", 3499, "Portable Bluetooth speaker with a dust- and water-resistant body and a carry strap.", "speaker",
  {"battery_hours": 12, "weight_g": 540, "water_resistance": "IP67", "output_w": 20, "bluetooth": "5.3", "wireless": True}, ["home", "outdoor", "travel"], 4.5,
  ["IP67 water and dust resistance", "20 W output", "Carry strap"], colours=["Coral"], stock=14, accent="#1c1c22", days=40)
P("VRT-1007", "Tempo Fitness Band", "Tempo", E, "Smart bands", 2199, "Fitness band with a colour display, step counting and a week-long listed battery life.", "band",
  {"battery_hours": 168, "weight_g": 25, "water_resistance": "5 ATM", "wireless": True}, ["gym", "running"], 4.0, ["Seven-day listed battery life", "5 ATM water resistance"],
  colours=["Teal", "Black"], per=8, accent="#c8f560", days=95)
P("VRT-1008", "VoltMax 20000 mAh Power Bank", "VoltMax", E, "Power banks", 1799, "20,000 mAh power bank with three ports and 22.5 W output.", "powerbank",
  {"capacity_mah": 20000, "output_w": 22.5, "weight_g": 440, "ports": 3, "charge_time_min": 400}, ["travel", "commute", "office"], 4.2, ["Three output ports", "22.5 W output"],
  pal="#6b4de6", stock=30, accent="#c8f560", days=55, hist=[(80, 1999)])
P("VRT-1009", "FastPort 33W USB-C Charger", "FastPort", E, "Chargers", 1099, "Compact 33 W USB-C wall charger with two ports.", "charger",
  {"output_w": 33, "ports": 2, "weight_g": 75}, ["travel", "office"], 4.3, ["33 W output", "Two ports", "75 g"], pal="#2540ff", stock=40, accent="#c8f560", days=18)
P("VRT-1010", "Glide Wireless Mouse", "Glide", E, "Mouse", 899, "Quiet-click wireless mouse with a Bluetooth connection.", "mouse",
  {"weight_g": 85, "battery_hours": 300, "wireless": True, "bluetooth": "5.0"}, ["office", "study"], 4.2, ["Quiet clicks", "85 g"], colours=["Black", "Grey"], per=14, accent="#2540ff", days=140)
# ------------------------------------------------------------------ Fashion
P("VRT-2001", "Classic White Cotton Shirt", "Loom & Lane", F, "Shirts", 1299, "Regular-fit cotton shirt with a spread collar.", "shirt",
  {"cotton_pct": 100, "fabric_gsm": 110, "machine_washable": True, "fit": "Regular"}, ["office", "formal"], 4.2, ["100% cotton", "Machine washable"],
  colours=["White", "Sky Blue"], sizes=S5, attrs={"material": "100% cotton"}, accent="#2540ff", days=180, hist=[(60, 1499)])
P("VRT-2002", "Linen Blend Casual Shirt", "Loom & Lane", F, "Shirts", 1799, "Relaxed-fit shirt in a cotton and linen blend.", "shirt",
  {"cotton_pct": 55, "fabric_gsm": 130, "machine_washable": True, "fit": "Relaxed"}, ["casual", "travel"], 4.1, ["55% cotton, 45% linen", "Relaxed fit"],
  colours=["Beige", "Olive"], sizes=S5, attrs={"material": "55% cotton, 45% linen"}, accent="#6b4226", days=88)
P("VRT-2003", "Cotton Crew T-Shirt", "Loom & Lane", F, "T-shirts", 699, "Everyday crew-neck t-shirt in heavyweight cotton.", "tshirt",
  {"cotton_pct": 100, "fabric_gsm": 180, "machine_washable": True, "fit": "Regular"}, ["casual", "daily"], 4.3, ["100% cotton", "180 GSM"],
  colours=["Black", "White", "Navy", "Grey"], sizes=S5, attrs={"material": "100% cotton"}, per=5, accent="#c8f560", featured=True, days=210, hist=[(120, 799), (60, 749)])
P("VRT-2004", "Premium Cotton Kurta", "Aaravi", F, "Kurtas", 2199, "Straight-cut cotton kurta with a mandarin collar and placket.", "kurta",
  {"cotton_pct": 100, "fabric_gsm": 140, "machine_washable": True, "fit": "Straight"}, ["casual", "gifting"], 4.4, ["100% cotton", "Mandarin collar"],
  colours=["Indigo", "White"], sizes=S5, attrs={"material": "100% cotton"}, accent="#f4b400", featured=True, days=20)
P("VRT-2005", "Stretch Slim Fit Jeans", "Denimo", F, "Jeans", 2299, "Slim-fit jeans in stretch denim with a mid rise.", "jeans",
  {"cotton_pct": 98, "fabric_gsm": 320, "machine_washable": True, "fit": "Slim"}, ["casual", "daily"], 4.0, ["98% cotton, 2% elastane", "Slim fit"],
  colours=["Indigo", "Black"], sizes=SZ, attrs={"material": "98% cotton, 2% elastane"}, per=3, accent="#f4b400", days=130)
P("VRT-2006", "Fleece Pullover Hoodie", "Northline", F, "Hoodies", 1999, "Brushed-fleece pullover hoodie with a kangaroo pocket.", "hoodie",
  {"cotton_pct": 80, "fabric_gsm": 320, "machine_washable": True, "fit": "Relaxed"}, ["casual", "travel"], 4.3, ["80% cotton, 20% polyester", "320 GSM fleece"],
  colours=["Charcoal", "Maroon"], sizes=S5, attrs={"material": "80% cotton, 20% polyester"}, accent="#c8f560", days=33)
P("VRT-2007", "Quick-Dry Training Tee", "Flexora", F, "T-shirts", 899, "Lightweight athletic-fit tee in recycled polyester for workouts.", "tshirt",
  {"weight_g": 130, "machine_washable": True, "fit": "Athletic"}, ["gym", "running"], 4.2, ["Recycled polyester", "Quick-dry fabric"],
  colours=["Coral", "Blue"], sizes=S5, attrs={"material": "Recycled polyester"}, accent="#1c1c22", days=60)
P("VRT-2008", "Lightweight Rain Jacket", "Northline", F, "Jackets", 2799, "Packable water-resistant jacket with a zip front and hood.", "jacket",
  {"weight_g": 320, "water_resistant": True, "machine_washable": True}, ["monsoon", "travel", "outdoor"], 4.1, ["Water-resistant shell", "Packable hood"],
  colours=["Olive", "Navy"], sizes=S5, attrs={"material": "Nylon"}, accent="#c8f560", days=9)
# ------------------------------------------------------------------ Footwear
P("VRT-3001", "Aero Run Blue Running Shoe", "Stridewell", FT, "Running shoes", 2499, "Lightweight mesh trainer for road running.", "sneaker_run",
  {"weight_g": 260, "cushioning": "Medium", "drop_mm": 8}, ["running", "gym"], 4.4, ["Breathable mesh upper", "260 g (UK 8)"], colours=["Blue"], sizes=SH,
  attrs={"use": "running"}, accent="#c8f560", per=4, featured=True, days=45)
P("VRT-3002", "Stride Pro Blue Running Shoe", "Stridewell", FT, "Running shoes", 3299, "Cushioned road shoe with a high-stack midsole.", "sneaker_run",
  {"weight_g": 285, "cushioning": "High", "drop_mm": 10}, ["running"], 4.1, ["High cushioning", "285 g (UK 8)"], colours=["Blue"], sizes=SH, attrs={"use": "running"}, accent="#e8604c", per=4, days=75)
P("VRT-3003", "Swift Blue Running Shoe", "Stridewell", FT, "Running shoes", 1899, "Entry-level trainer. Currently sold out in the demo store.", "sneaker_run",
  {"weight_g": 240, "cushioning": "Low", "drop_mm": 6}, ["running", "casual"], 3.9, ["240 g (UK 8)", "Low-profile midsole"], colours=["Blue"], sizes=SH, attrs={"use": "running"},
  out=True, accent="#1c1c22", days=190)
P("VRT-3004", "Daily Canvas Sneakers", "Kickside", FT, "Sneakers", 1599, "Low-top canvas sneakers with a vulcanised sole.", "sneaker_canvas",
  {"weight_g": 380}, ["casual", "daily"], 4.2, ["Cotton canvas upper", "Vulcanised rubber sole"], colours=["White", "Black"], sizes=SH, attrs={"material": "Cotton canvas"}, per=3, accent="#e8604c", days=52)
P("VRT-3005", "Monsoon Slides", "Kickside", FT, "Sandals", 799, "Quick-drying EVA slides that are easy to wash.", "slide",
  {"weight_g": 300, "water_resistant": True}, ["monsoon", "home", "casual"], 4.0, ["Quick-drying EVA", "Easy to wash"], colours=["Teal", "Navy"], sizes=SH, attrs={"material": "EVA foam"},
  per=5, accent="#f4b400", days=14)
P("VRT-3006", "Oxford Leather Formal Shoes", "Brogue & Co", FT, "Formal shoes", 3499, "Lace-up oxford shoes with a leather upper and rubber sole.", "formal_shoe",
  {"weight_g": 620}, ["formal", "office"], 4.3, ["Leather upper", "Cushioned insole"], colours=["Brown", "Black"], sizes=SH, attrs={"material": "Leather"}, per=2, accent="#d9c7a3", days=105)
# ------------------------------------------------------------------ Home & Kitchen
P("VRT-4001", "Steel Water Bottle 1L", "Hydra", H, "Bottles", 599, "Single-wall stainless steel bottle with a leak-resistant cap. Not insulated.", "bottle",
  {"capacity_ml": 1000, "weight_g": 380, "bpa_free": True}, ["gym", "travel", "office", "outdoor"], 4.2, ["Stainless steel", "1 litre", "BPA-free cap"], colours=["Silver", "Black"],
  attrs={"material": "Stainless steel"}, per=12, accent="#2540ff", days=230)
P("VRT-4002", "Vacuum Insulated Bottle 750 ml", "Hydra", H, "Bottles", 1299, "Double-wall vacuum bottle that keeps drinks cold or hot for hours.", "bottle_slim",
  {"capacity_ml": 750, "insulation_hours": 18, "weight_g": 420, "bpa_free": True}, ["travel", "outdoor", "office", "gym"], 4.5, ["Up to 18 hours listed insulation", "750 ml"],
  colours=["Teal", "Black"], attrs={"material": "Stainless steel"}, per=9, accent="#c8f560", featured=True, days=22, hist=[(70, 1399)])
P("VRT-4003", "Non-Stick Fry Pan 24 cm", "Kitchenly", H, "Cookware", 999, "24 cm non-stick fry pan with a heat-resistant handle.", "pan",
  {"weight_g": 780, "induction_compatible": True, "dishwasher_safe": False}, ["home", "cooking"], 4.0, ["Induction compatible", "Non-stick coating"], pal="#6a6f7c", stock=22, accent="#1c1c22", days=170)
P("VRT-4004", "Electric Kettle 1.5 L", "Kitchenly", H, "Kettles", 1199, "1.5 litre electric kettle with auto shut-off.", "kettle",
  {"capacity_ml": 1500, "power_w": 1500, "weight_g": 900}, ["home", "office"], 4.2, ["1500 W", "Auto shut-off"], pal="#e8604c", stock=16, accent="#1f2a44", days=115)
P("VRT-4005", "Ceramic Coffee Mug Set of 4", "Kitchenly", H, "Drinkware", 799, "Set of four 300 ml ceramic mugs. Dishwasher safe.", "mugs",
  {"capacity_ml": 300, "dishwasher_safe": True}, ["home", "gifting"], 4.3, ["Set of four", "Dishwasher safe"], pal="#1b8a8a", stock=20, accent="#f4b400", days=68)
P("VRT-4006", "LED Desk Lamp with Dimmer", "Lumen & Co", H, "Lamps", 1599, "Adjustable-arm LED desk lamp with a dimmer and three colour temperatures.", "lamp",
  {"brightness_lumens": 600, "power_w": 9, "weight_g": 750}, ["study", "office", "home"], 4.4, ["600 lumens", "Dimmable", "Adjustable arm"], colours=["Black", "White"], per=8, accent="#f4b400",
  featured=True, days=30)
P("VRT-4007", "Cotton Bedsheet Set (Double)", "Restwell", H, "Bedding", 1899, "Double bedsheet with two pillow covers in soft cotton.", "bedsheet",
  {"cotton_pct": 100, "fabric_gsm": 180, "machine_washable": True}, ["home"], 4.1, ["100% cotton", "Includes two pillow covers"], colours=["Grey", "Teal"], attrs={"material": "100% cotton"},
  per=7, accent="#c8f560", days=150)
P("VRT-4008", "Airtight Storage Jars (Set of 3)", "Kitchenly", H, "Storage", 699, "Set of three airtight jars in 500 ml, 750 ml and 1 L sizes. Dishwasher safe.", "jars",
  {"bpa_free": True, "dishwasher_safe": True}, ["home", "cooking"], 4.2, ["Three sizes", "Airtight lids"], pal="#8ec5ff", stock=25, accent="#2540ff", days=80)
# ------------------------------------------------------------------ Beauty & personal care
P("VRT-5001", "Daily SPF 50 Sunscreen 50 ml", "Dewlight", B, "Sunscreen", 549, "Lightweight daily sunscreen with SPF 50. Fragrance free.", "tube",
  {"spf": 50, "volume_ml": 50, "fragrance_free": True}, ["outdoor", "daily"], 4.2, ["SPF 50", "Fragrance free"], pal="#f4b400", stock=45, accent="#e8604c", days=35)
P("VRT-5002", "Gentle Foaming Face Wash 150 ml", "Dewlight", B, "Cleansers", 349, "Gentle foaming face wash for daily use. Fragrance free.", "pump_bottle",
  {"volume_ml": 150, "fragrance_free": True}, ["daily"], 4.1, ["Fragrance free", "Pump bottle"], pal="#e8604c", stock=50, accent="#1f2a44", days=120)
P("VRT-5003", "Vitamin C Face Serum 30 ml", "Dewlight", B, "Serums", 899, "Brightening face serum with vitamin C in a dropper bottle.", "dropper",
  {"volume_ml": 30, "fragrance_free": True}, ["daily"], 3.9, ["30 ml dropper bottle", "Fragrance free"], pal="#16a085", stock=26, accent="#f4b400", days=100)
P("VRT-5004", "Cordless Beard Trimmer", "Groomwell", B, "Grooming", 1499, "Rechargeable beard trimmer with adjustable combs and a washable head.", "trimmer",
  {"runtime_min": 90, "weight_g": 150, "water_resistant": True, "wireless": True}, ["travel", "daily"], 4.2, ["90-minute listed runtime", "Washable head"], pal="#6b4de6", stock=19, accent="#c8f560", days=47)
P("VRT-5005", "Herbal Shampoo 340 ml", "Dewlight", B, "Hair care", 449, "Everyday herbal shampoo in a flip-cap bottle.", "shampoo",
  {"volume_ml": 340}, ["daily"], 4.0, ["340 ml", "Flip-cap bottle"], pal="#2e9e6b", stock=38, accent="#f4b400", days=140)
# ------------------------------------------------------------------ Sports & fitness
P("VRT-6001", "Non-Slip Yoga Mat 6 mm", "Flexora", SP, "Yoga mats", 899, "6 mm non-slip yoga mat with a carry strap. Currently sold out in the demo store.", "yoga_mat",
  {"thickness_mm": 6, "length_m": 1.83, "weight_g": 1100, "non_slip": True}, ["yoga", "home", "gym"], 4.3, ["6 mm cushioning", "Non-slip surface"], pal="#6b4de6", stock=0, accent="#c8f560", days=90)
P("VRT-6002", "Adjustable Dumbbell Set 20 kg", "Flexora", SP, "Weights", 3999, "Adjustable dumbbell set with two handles and plates, up to 20 kg in total.", "dumbbell",
  {"max_load_kg": 20}, ["gym", "home"], 4.4, ["Adjustable up to 20 kg", "Knurled grip"], pal="#8a8f9c", stock=4, accent="#e8604c", days=64)
P("VRT-6003", "Speed Skipping Rope", "Flexora", SP, "Cardio", 349, "Adjustable speed rope with ball-bearing handles.", "rope",
  {"length_m": 2.8, "weight_g": 120}, ["gym", "running"], 4.0, ["Adjustable length", "Ball-bearing handles"], pal="#e8604c", stock=35, accent="#1f2a44", days=170)
P("VRT-6004", "Resistance Bands (Set of 5)", "Flexora", SP, "Bands", 799, "Five resistance bands from light to extra heavy, with a carry pouch.", "bands",
  {"max_load_kg": 35, "weight_g": 300}, ["gym", "home", "travel", "yoga"], 4.2, ["Five resistance levels", "Carry pouch"], pal="#1b8a8a", stock=25, accent="#f4b400", days=58)
P("VRT-6005", "Training Football Size 5", "Kickside", SP, "Balls", 699, "Size 5 machine-stitched training football.", "football",
  {"weight_g": 430}, ["outdoor"], 4.0, ["Size 5", "Machine stitched"], pal="#6b4de6", stock=18, accent="#c8f560", days=205)
P("VRT-6006", "Foam Roller 45 cm", "Flexora", SP, "Recovery", 999, "45 cm textured foam roller for stretching and recovery.", "foam_roller",
  {"length_m": 0.45, "max_load_kg": 120, "weight_g": 480}, ["gym", "yoga"], 4.1, ["Textured surface", "45 cm"], pal="#2540ff", stock=12, accent="#c8f560", days=77)
# ------------------------------------------------------------------ Books & stationery
P("VRT-7001", "A5 Dotted Notebook (Pack of 2)", "Inkwell", ST, "Notebooks", 449, "Two A5 dotted notebooks with 100 GSM paper and an elastic closure.", "notebook",
  {"pages": 160, "paper_gsm": 100}, ["study", "office"], 4.4, ["160 pages each", "100 GSM paper"], colours=["Black", "Teal"], per=30, accent="#2540ff", days=26)
P("VRT-7002", "Gel Pens, Pack of 10", "Inkwell", ST, "Pens", 199, "Ten smooth-writing gel pens in assorted colours.", "pens",
  {"refillable": False}, ["study", "office"], 4.1, ["Ten colours", "0.5 mm tip"], pal="#2540ff", stock=80, accent="#e8604c", days=190)
P("VRT-7003", "Weekly Planner Desk Pad", "Inkwell", ST, "Planners", 349, "52-page tear-off weekly planner for your desk.", "planner",
  {"pages": 52, "paper_gsm": 90}, ["study", "office", "home"], 4.0, ["52 weekly pages", "Tear-off sheets"], pal="#e8604c", stock=28, accent="#2540ff", days=112)
P("VRT-7004", "The Quiet Ledger (Novel)", "Marlow Press", ST, "Books", 399, "A fictional demonstration title: a paperback novel of 312 pages.", "book",
  {"pages": 312}, ["gifting", "home"], 4.2, ["Paperback", "312 pages"], pal="#1b8a8a", stock=15, accent="#f4b400", days=19)
P("VRT-7005", "Pastel Highlighter Set (6)", "Inkwell", ST, "Pens", 249, "Six pastel highlighters with chisel tips.", "highlighters",
  {"refillable": False}, ["study", "office"], 4.1, ["Six pastel colours", "Chisel tip"], pal="#c8f560", stock=50, accent="#6b4de6", days=84)
# ------------------------------------------------------------------ Bags
P("VRT-8001", "Metro Laptop Backpack 25 L", "Carryall", BG, "Backpacks", 2299, "25 litre backpack with a padded compartment for laptops up to 15.6 inch and a water-resistant fabric.", "backpack",
  {"volume_l": 25, "laptop_max_inch": 15.6, "water_resistant": True, "weight_g": 780, "compartments": 4}, ["study", "commute", "office", "travel"], 4.4,
  ["Fits laptops up to 15.6 inch", "Water-resistant fabric", "Four compartments"], colours=["Black", "Navy"], per=8, accent="#c8f560", featured=True, days=16)
P("VRT-8002", "Campus Backpack 20 L", "Carryall", BG, "Backpacks", 1299, "20 litre everyday backpack with a padded laptop sleeve for up to 14 inch.", "backpack",
  {"volume_l": 20, "laptop_max_inch": 14, "water_resistant": False, "weight_g": 600, "compartments": 3}, ["study", "commute"], 4.1, ["Fits laptops up to 14 inch", "Three compartments"],
  colours=["Grey", "Maroon"], per=10, accent="#2540ff", days=125)
P("VRT-8003", "Canvas Tote Bag", "Carryall", BG, "Totes", 599, "Roomy cotton canvas tote with an inside pocket.", "tote",
  {"volume_l": 15, "water_resistant": False, "weight_g": 280}, ["casual", "daily"], 4.0, ["Cotton canvas", "Inside pocket"], pal="#1c1c22", stock=40, accent="#2540ff", days=155, attrs={"material": "Cotton canvas"})
P("VRT-8004", "Weekender Duffel 35 L", "Carryall", BG, "Duffels", 2799, "35 litre duffel with a shoe compartment and a detachable shoulder strap.", "duffel",
  {"volume_l": 35, "water_resistant": True, "weight_g": 950, "compartments": 2}, ["gym", "travel"], 4.3, ["35 litres", "Separate shoe compartment"], pal="#d8c3a5", stock=11, accent="#1c1c22", days=41)


def build():
    OUT_IMG.mkdir(parents=True, exist_ok=True)
    for old in OUT_IMG.glob("*.svg"):
        old.unlink()
    records = []
    for rec, kind, pal in PRODUCTS:
        records.append(rec)
        tint = TINT[rec["category"]]
        for v in (1, 2, 3):
            (OUT_IMG / f"{rec['id']}-{v}.svg").write_text(art.render(kind, pal, v, tint), encoding="utf-8")
    ids = [r["id"] for r in records]
    assert len(ids) == len(set(ids)), "duplicate ids"
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "catalogue.json").write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT_DIR / "manifest.json").write_text(json.dumps({"source": "demo-store", "label": "Verity demo store (synthetic data)"}, indent=1) + "\n", encoding="utf-8")
    kb = sum(f.stat().st_size for f in OUT_IMG.glob("*.svg")) / 1024
    print(f"{len(records)} products, {len(records) * 3} images ({kb:.0f} KB total)")


if __name__ == "__main__":
    build()
