"""Language-understanding helpers that need no catalogue access.

Everything here only *widens understanding of the question* (what the shopper means). It never produces facts: every answer is
still composed from catalogue / policy records in assistant.py and carries a citation.

  * GENERAL_STOP   filler words that must never be treated as product terms ("something", "mujhe", "every", ...)
  * AUDIENCE       recipients / genders; the catalogue does not record them, so they are noted, never silently dropped
  * CONCEPTS       need -> catalogue vocabulary ("music" -> headphone/earbud/speaker, "rainy day" -> monsoon/rain)
  * price ranges   "between 500 and 1000", "above 4000", "under 2k"
  * rank cues      "longest battery", "lightest", "most powerful"
  * references     "the first one", "the first two", "it", "these"
  * small talk     greetings, thanks, "what can you do", off-topic requests
"""
import re

I = re.I

GENERAL_STOP = frozenset("""
something anything everything nothing stuff thing things item items product products
every each some someone anyone anybody somebody everyone
mujhe mereko mujhko humko hume ek koi wala wali wale dikha dikhaiye dikhana dena chahta chahti kuch
we us our ours he she they him her his their
if but so because while when then as by into onto out up down off over again still even ever never always usually maybe probably perhaps sure
now right just really very quite little bit lot lots
morning evening afternoon night today tonight tomorrow yesterday week weekend
buy purchase use used using work works working
make made go going come comes take put try think know like love wish hope ask
let lets help check see look looks shopping shop store online
rupee rupees rupaye long
should would could shall may might must day night read reads reading verity after before during until from protect season start begin doing getting pair pairs piece pieces couple don doesn didn isn aren wasn accessories accessory accessorie idea ideas lover fan kitne kitni kitna kaisa kaise kab
""".split())

# Context words that never name a product on their own ("phone charger"): ignored when another product word is present.
SOFT = frozenset("phone phones mobile smartphone smartphones".split())

AUDIENCE = frozenset("""
men mens man male women womens woman female ladies lady boys boy girls girl kids kid children child baby toddler unisex
dad father papa mom mother mum mummy wife husband brother sister friend boyfriend girlfriend son daughter grandma grandpa grandmother grandfather
boss teacher colleague bhai beta
""".split())

# (regex, label, catalogue tokens). A product satisfies the concept when it carries ANY of the tokens as positive evidence.
# Order matters: specific patterns first. Matched text is removed from the query before the remaining words are tokenised.
CONCEPTS = [
    (r"keeps?\s+(?:my\s+|the\s+|a\s+)?(?:drinks?|water|tea|coffee|beverages?|liquids?)\s+(?:hot|cold|warm|chilled)|(?:keeps?|keeping)\s+(?:hot|cold)|\b(?:thermos|flask|insulated|(?:hot|cold) drinks?)\b",
     "keeps drinks hot or cold", ["insulated", "insulation"]),
    (r"\b(?:waterproof|water[- ]?proof|water[- ]?resistan\w*|splash[- ]?proof|sweat[- ]?proof)\b", "waterproof", ["resistant", "resistance", "waterproof"]),
    (r"\b(?:music|songs?|audio|podcasts?|listen(?:ing)?(?:\s+to)?)\b", "music", ["headphone", "earbud", "speaker"]),
    (r"\b(?:earphones?|headsets?|earpieces?)\b", "earphones", ["earbud", "headphone"]),
    (r"\b(?:jog(?:ging|s|ger)?|marathon|sprint(?:ing)?)\b", "jogging", ["running", "gym"]),
    (r"\b(?:work(?:ing)?[ -]?outs?|exercis\w+)\b", "working out", ["gym", "yoga"]),
    (r"\b(?:carry(?:ing)?|luggage)\b", "carrying", ["bag", "backpack", "tote", "duffel"]),
    (r"\b(?:rain(?:y|coat)?|monsoons?|drizzle)\b", "rain", ["monsoon", "rain"]),
    (r"\b(?:gifts?|gifting|birthday|anniversary)\b", "gifting", ["gifting"]),
    (r"\b(?:school|college|campus|students?|universit\w+|exams?|homework)\b", "study", ["study"]),
    (r"\b(?:skin\s?care|skin|moisturi[sz]\w*)\b", "skin care", ["sunscreen", "serum", "cleanser"]),
    (r"\b(?:trips?|vacations?|holidays?|tours?)\b", "travel", ["travel"]),
    (r"\bstretch(?:ing|es)?\b", "stretching", ["roller", "yoga", "band"]),
    (r"\b(?:sun(?:screen|block|burn|tan)?|uv|tanning)\b", "sun protection", ["sunscreen"]),
    (r"\b(?:writ(?:e|es|ing)|notes?|jot(?:ting)?|stationery)\b", "writing", ["pen", "notebook", "highlighter"]),
    (r"\bwithout\s+(?:a\s+)?(?:cord|wire|cable)s?\b", "cordless", ["cordless", "wireless"]),
    (r"\b(?:hik(?:e|es|ing)|trek(?:king)?|camp(?:ing)?|picnics?|outdoors?)\b", "outdoors", ["outdoor"]),
    (r"\b(?:organi[sz]\w*|tidy\w*|declutter\w*)\b", "organising", ["storage", "jar"]),
    (r"\bbed(?:room)?s?\b", "bedding", ["bedsheet", "bedding"]),
    (r"\b(?:slippers?|flip[- ]?flops?|chappals?)\b", "slippers", ["sandal", "slide"]),
    (r"\b(?:chai|tea)\b", "tea", ["kettle", "mug"]),
    (r"\b(?:diary|journal)\b", "journal", ["notebook", "planner"]),
    (r"\b(?:heavy|weigh(?:s|t)?)\b", "weight", ["weight", "kg"]),
]
# Concepts whose wording is NOT what the catalogue says ("waterproof" vs "water-resistant"): never presented as an exact match.
APPROX = frozenset({"waterproof"})
_CONCEPTS = [(re.compile(p, I), label, toks) for p, label, toks in CONCEPTS]


def extract_concepts(text: str):
    """Return (text with concept phrases removed, [(label, frozenset(tokens)), ...])."""
    found = []
    for rx, label, toks in _CONCEPTS:
        if rx.search(text):
            found.append((label, frozenset(toks)))
            text = rx.sub(" ", text)
    return text, found


# ---------------------------------------------------------------- price ranges
_CUR = r"(?:rs\.?|inr|₹|rupees?|rupaye)?\s*"
# A number followed by one of these is a quantity ("at least 25 hours", "over 15 inch"), never a price.
_UNIT = r"(?!\s*(?:hours?|hrs?|h\b|mah|w\b|watts?|gb|mb|tb|kg|g\b|ml|l\b|litres?|liters?|mm|cm|inch(?:es)?|%|percent|days?|months?|years?|min(?:ute)?s?\b|pages?|gsm|x\b|pcs|pieces?|stars?))"
_N = r"(\d[\d,]*(?:\.\d+)?)(?![\d,])\s*(k\b)?" + _UNIT
RANGE_A = re.compile(rf"\b(?:between|from)\s+{_CUR}{_N}\s*{_CUR}(?:and|to|-|–)\s*{_CUR}{_N}\s*(?:rs|rupees?|inr)?", I)
RANGE_B = re.compile(rf"(?<![\w.]){_CUR}{_N}\s*(?:to|-|–)\s*{_CUR}{_N}\s*(?:rs|rupees?|inr)?(?![\w.])", I)
LOWER = re.compile(rf"\b(?:above|over|more than|greater than|at least|minimum|min|starting (?:from|at)|costing more than)\s+{_CUR}{_N}\s*(?:rs|rupees?|inr)?", I)
UPPER_K = re.compile(rf"\b(?:under|below|less than|upto|up to|within|max(?:imum)?|budget(?: of)?)\s*{_CUR}(\d[\d,]*(?:\.\d+)?)\s*(k\b)", I)


def _val(num: str, k) -> float:
    v = float(num.replace(",", ""))
    return v * 1000 if k else v


def parse_range(text: str):
    """(low, high) in rupees from range phrases; either may be None. Does not look at plain 'under X' (assistant.parse_budget does)."""
    m = RANGE_A.search(text) or RANGE_B.search(text)
    if m:
        a, b = _val(m.group(1), m.group(2)), _val(m.group(3), m.group(4))
        if m.re is RANGE_B and not (a >= 50 and b >= 50):      # "5-6" or "1-2" are not prices
            m = None
        else:
            return (min(a, b), max(a, b))
    m = LOWER.search(text)
    lo = _val(m.group(1), m.group(2)) if m else None
    k = UPPER_K.search(text)
    hi = _val(k.group(1), k.group(2)) if k else None
    return (lo, hi) if (lo is not None or hi is not None) else (None, None)


def strip_price(text: str) -> str:
    for rx in (RANGE_A, RANGE_B, LOWER, UPPER_K):
        text = rx.sub(" ", text)
    return text


# ---------------------------------------------------------------- ranking cues
_HIGH = r"(?:longest|largest|biggest|highest|greatest|most|best|maximum|max|strongest|longer|larger|bigger|higher)"
_LOW = r"(?:shortest|smallest|lowest|least|minimum|min|fastest|quickest|smaller|shorter|lower)"
SPEC_WORDS = [
    (r"batter(?:y|ies)(?:\s+(?:life|backup|hours?))?|battery backup|last(?:s|ing)?", ["battery_hours"], "battery life"),
    (r"keeps?\s+\w+\s+(?:cold|hot|warm)|insulat\w+", ["insulation_hours"], "insulation time"),
    (r"(?:charging|charge)\s+time|charg\w*\s+(?:the\s+)?(?:fast|quick)\w*|(?:fast|quick)(?:est)?\s+charg\w*", ["charge_time_min"], "charging time"),
    (r"capacity", ["capacity_mah", "capacity_ml", "volume_l"], "capacity"),
    (r"volume|size|space|roomy", ["volume_l", "capacity_ml", "capacity_mah"], "size"),
    (r"power(?:ful)?|output|watt\w*", ["output_w", "power_w"], "power output"),
    (r"bright\w*", ["brightness_lumens"], "brightness"),
    (r"spf|sun protection", ["spf"], "SPF"),
    (r"run\s?time", ["runtime_min"], "runtime"),
    (r"weigh\w*|heav(?:y|ier|iest)|light(?:est|er)", ["weight_g"], "weight"),
    (r"cotton", ["cotton_pct"], "cotton content"),
    (r"(?:max(?:imum)?\s+)?load", ["max_load_kg"], "maximum load"),
    (r"pages?", ["pages"], "page count"),
    (r"thick\w*", ["thickness_mm"], "thickness"),
]
_SPEC = [(re.compile(p, I), keys, label) for p, keys, label in SPEC_WORDS]
_HI, _LO = re.compile(rf"\b{_HIGH}\b", I), re.compile(rf"\b{_LOW}\b", I)
_LIGHT, _HEAVY = re.compile(r"\blight(?:est|er)\b", I), re.compile(r"\bheav(?:iest|ier)\b", I)
PRICEY = re.compile(r"\b(?:most expensive|priciest|costliest|highest[- ]priced?|most costly)\b", I)
SIZE_ONLY = re.compile(r"\b(?:largest|biggest|smallest)\b", I)


def parse_rank(text: str):
    """A superlative over a catalogue spec: {'keys': [spec keys], 'dir': 'max'|'min', 'label': str, 'rest': text with the cue removed}.
    Needs BOTH a comparative cue and a spec word ("longest battery"), so "battery life of the Halo" is never a ranking."""
    heavy, light = _HEAVY.search(text), _LIGHT.search(text)
    hi, lo = _HI.search(text), _LO.search(text)
    if not (hi or lo or heavy or light):
        return None
    spec = next(((keys, label, rx) for rx, keys, label in _SPEC if rx.search(text)), None)
    if spec is None and SIZE_ONLY.search(text):
        spec = (["volume_l", "capacity_ml", "capacity_mah"], "size", None)
    if spec is None:
        return None
    keys, label, rx = spec
    direction = "min" if (light or (lo and not hi)) else "max"
    if label == "charging time":
        direction = "min"              # a shorter charge is the better one
    if label == "weight" and not (heavy or light):
        direction = "max" if (hi and not lo) else "min"
    rest = text
    for r in (rx, _HI, _LO, _LIGHT, _HEAVY):
        if r is not None:
            rest = r.sub(" ", rest)
    return {"keys": keys, "dir": direction, "label": label, "rest": rest}


# ---------------------------------------------------------------- references to earlier results
ORDINAL = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3, "last": -1}
_ORD = re.compile(r"\b(first|second|third|fourth|last|1st|2nd|3rd|4th)\b(?:\s+(?:one|option|product|item|result|pair))?", I)
_FIRST_N = re.compile(r"\b(?:first|top)\s+(two|2|three|3|four|4)\b|\b(?:both|the two|these two|those two|the 2)\b", I)
_PLURAL_REF = re.compile(r"\b(?:these|those|them|all of them|all of these|each)\b", I)
_SINGLE_REF = re.compile(r"\b(?:it|its|this|that|this one|that one|this product|that product|the same|same one)\b", I)
_NUMW = {"two": 2, "2": 2, "three": 3, "3": 3, "four": 4, "4": 4}


def parse_refs(text: str):
    """What the message points back at: {'indexes': [int], 'plural': bool, 'single': bool, 'n': int|None, 'rest': text without the reference words}."""
    out = {"indexes": [], "plural": False, "single": False, "n": None}
    rest = text
    m = _FIRST_N.search(text)
    if m:
        out["n"] = _NUMW.get((m.group(1) or "two").lower(), 2)
        rest = _FIRST_N.sub(" ", rest)
    else:
        for m in _ORD.finditer(text):
            out["indexes"].append(ORDINAL[m.group(1).lower()])
        rest = _ORD.sub(" ", rest)
        if _PLURAL_REF.search(text):
            out["plural"] = True
    if _SINGLE_REF.search(text) and not out["indexes"]:
        out["single"] = True
    return out, rest


CART = re.compile(r"\b(?:add|put|place|drop)\b.*\b(?:cart|basket)\b|\b(?:buy|purchase|order|take|get)\b\s+(?:it|this|that|the (?:first|second|third|last|cheaper|cheapest)|them)\b|\bi(?:'ll| will) (?:take|buy|get)\b", I)

# ---------------------------------------------------------------- small talk
GREETING = re.compile(r"^\W*(?:hi+|hello+|hey+|hiya|namaste|namaskar|hola|yo|sup|good\s+(?:morning|afternoon|evening|night))\b[\s,!.]*(?:there|verity|team|everyone|bot|assistant)?\W*$", I)
LEADING_GREETING = re.compile(r"^\W*(?:hi+|hello+|hey+|namaste)\b[\s,!.]+", I)
THANKS = re.compile(r"^\W*(?:thanks?|thank\s+you|thx|ty|shukriya|dhanyavaad|dhanyavad|great|awesome|perfect|cool|nice|ok(?:ay)?|got it|alright)\b[^?]{0,40}$", I)
BYE = re.compile(r"^\W*(?:bye+|goodbye|see\s+you|good\s?night|cya|tata|alvida)\b[^?]{0,30}$", I)
IDENTITY = re.compile(r"\b(?:who|what)\s+(?:are|r)\s+(?:you|u)\b|\byour\s+name\b|\bare\s+(?:you|u)\s+(?:a\s+|an\s+)?(?:bot|robot|ai|human|real|person|machine)\b|\bare you real\b", I)
HELP = re.compile(r"\bwhat\s+(?:can|do)\s+you\s+(?:do|help)|\bhow\s+(?:can|do)\s+you\s+help|\bhow\s+do\s+you\s+work\b|^\W*help\W*$|\bwhat\s+(?:do|can)\s+i\s+ask\b|\bwhat\s+do\s+you\s+(?:sell|stock|have|offer)\W*$|\bwhat\s+products\b|\bwhat\s+(?:is|are)\s+(?:in\s+)?(?:your|the)\s+(?:store|catalogue|catalog|range)\b", I)
OFFTOPIC = re.compile(
    r"\bjokes?\b|\bweather\b|\bnews\b|\bprime minister\b|\bpresident of\b|\bcapital of\b|\bhoroscope\b|\bcricket score\b|\bbitcoin\b|\bstock market\b|\btranslate\b"
    r"|\bwrite\s+(?:me\s+)?(?:a|an|some)?\s*(?:python|java|javascript|code|script|program|essay|poem|story|song|email|letter)\b"
    r"|\b\d+\s*(?:\+|\*|×|÷|/|times|plus|minus|multiplied by|divided by)\s*\d+\b|\bwho (?:is|was) the\b.*\b(?:minister|president|king|actor|founder)\b"
    r"|\b(?:book|reserve)\b.*\b(?:flights?|hotels?|tickets?|cab|taxi|table|train)\b|\bhistory of\b|\bmovie|\bplay (?:a )?(?:song|game|video)\b", I)
SEND_BACK = re.compile(r"\b(?:send(?:ing)?|give|giving|take|taking|sent|ship(?:ping)?)\s+(?:\w+\s+){0,2}back\b|\bmoney back\b|\bget my money\b", I)
DAMAGE = re.compile(r"\b(?:damaged|defective|broken|faulty|wrong (?:item|product)|missing (?:item|part)|not working|stopped working)\b", I)


def smalltalk_kind(text: str):
    t = text.strip()
    if GREETING.match(t):
        return "greeting"
    if BYE.match(t):
        return "bye"
    if THANKS.match(t) and len(t.split()) <= 7:
        return "thanks"
    if IDENTITY.search(t):
        return "identity"
    if HELP.search(t):
        return "help"
    if OFFTOPIC.search(t):
        return "offtopic"
    return None


QUESTION = re.compile(r"^\W*(?:is|are|was|does|do|did|can|could|will|would|has|have|what|which|how|tell me|kya|should)\b|\?\s*$", I)
SIZE_Q = re.compile(r"\bsize\s+(xxs|xs|xxxl|xxl|xl|s|m|l|\d{1,2})\b|\b(?:in|available in|comes? in|come in|for)\s+(?:a\s+)?(xxs|xs|xxxl|xxl|xl|s|m|l|\d{2})\b(?!\s*(?:inch|in|cm|mm|kg|g|l\b))", I)
SIZES_ASK = re.compile(r"\bsizes\b|\bwhat sizes?\b|\bwhich sizes?\b", I)
COLOUR_ASK = re.compile(r"\bcolou?rs?\b", I)
