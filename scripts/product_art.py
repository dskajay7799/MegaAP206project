"""Procedural product illustrations for the Verity demo store.

These are NOT photographs. They are original, license-free vector illustrations rendered with studio-style gradients so the
storefront has consistent, lightweight imagery (3 views per product: front, angled on dark, close-up detail).
Replace any product image with real photography through the admin panel (https URL) or by editing demo_store/catalogue.json.
"""
import math

W = 600


# ---------------------------------------------------------------- colour helpers
def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(r, g, b):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in (r, g, b))


def mix(a, b, t):
    ra, rb = _rgb(a), _rgb(b)
    return _hex(*[ra[i] + (rb[i] - ra[i]) * t for i in range(3)])


def lighten(h, t):
    return mix(h, "#ffffff", t)


def darken(h, t):
    return mix(h, "#000000", t)


class Canvas:
    def __init__(self):
        self.defs, self.n = [], 0

    def _id(self, p):
        self.n += 1
        return f"{p}{self.n}"

    def lin(self, c1, c2, x1=0, y1=0, x2=0, y2=1, mid=None):
        i = self._id("g")
        stops = f'<stop offset="0" stop-color="{c1}"/>' + (f'<stop offset=".5" stop-color="{mid}"/>' if mid else "") + f'<stop offset="1" stop-color="{c2}"/>'
        self.defs.append(f'<linearGradient id="{i}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">{stops}</linearGradient>')
        return f"url(#{i})"

    def rad(self, c1, c2, cx=.5, cy=.4, r=.7):
        i = self._id("r")
        self.defs.append(f'<radialGradient id="{i}" cx="{cx}" cy="{cy}" r="{r}"><stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></radialGradient>')
        return f"url(#{i})"

    def blur(self, std):
        i = self._id("f")
        self.defs.append(f'<filter id="{i}" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="{std}"/></filter>')
        return f"url(#{i})"

    def shadow(self):
        i = self._id("s")
        self.defs.append(f'<filter id="{i}" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="14" stdDeviation="12" flood-color="#0b1026" flood-opacity=".28"/></filter>')
        return f"url(#{i})"

    def pattern_dots(self, color, size=14, r=3.2):
        i = self._id("p")
        self.defs.append(f'<pattern id="{i}" width="{size}" height="{size}" patternUnits="userSpaceOnUse"><circle cx="{size / 2}" cy="{size / 2}" r="{r}" fill="{color}"/></pattern>')
        return f"url(#{i})"


def gloss(d, op=.28):
    return f'<path d="{d}" fill="#fff" opacity="{op}"/>'


def rr(x, y, w, h, r, fill, extra=""):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" {extra}/>'


# ---------------------------------------------------------------- drawers: each returns (svg_body, shadow_mode)
def headphones(cv, p, wired=False):
    a, b = p["a"], p["b"]
    cup = cv.lin(lighten(a, .22), darken(a, .3), 0, 0, 1, 1)
    band = cv.lin(lighten(a, .3), darken(a, .15), 0, 0, 0, 1)
    s = f'<path d="M168 352 C168 128 432 128 432 352" fill="none" stroke="{darken(a, .4)}" stroke-width="34" stroke-linecap="round"/>'
    s += f'<path d="M168 352 C168 140 432 140 432 352" fill="none" stroke="{band}" stroke-width="24" stroke-linecap="round"/>'
    s += f'<path d="M204 238 C252 182 348 182 396 238" fill="none" stroke="{b}" stroke-width="9" stroke-linecap="round" opacity=".95"/>'
    for x, px in ((112, 200), (388, 392)):
        s += rr(x, 306, 100, 150, 44, cup)
        s += f'<ellipse cx="{px}" cy="381" rx="15" ry="58" fill="{darken(a, .55)}"/>'
        s += f'<circle cx="{x + 50}" cy="381" r="26" fill="none" stroke="{b}" stroke-width="7"/><circle cx="{x + 50}" cy="381" r="9" fill="{b}"/>'
        s += gloss(f"M{x + 14} 340 Q{x + 22} 318 {x + 52} 316 Q{x + 24} 330 {x + 22} 372 Z", .3)
    if wired:
        s += f'<path d="M162 456 C150 540 250 560 330 535 S460 520 470 560" fill="none" stroke="{darken(a, .5)}" stroke-width="7" stroke-linecap="round"/>'
        s += rr(462, 556, 26, 30, 6, darken(a, .5))
    return s, "floor"


def earbuds(cv, p):
    a, b = p["a"], p["b"]
    case = cv.lin(lighten(a, .25), darken(a, .25), 0, 0, 1, 1)
    bud = cv.lin(lighten(a, .35), darken(a, .1), 0, 0, 1, 1)
    s = rr(180, 330, 240, 150, 62, case)
    s += f'<path d="M180 392 Q300 372 420 392" fill="none" stroke="{darken(a, .35)}" stroke-width="3"/>'
    s += f'<circle cx="300" cy="438" r="7" fill="{b}"/>'
    s += gloss("M206 352 Q300 330 394 350 Q300 344 206 372 Z", .3)
    for cx, rot in ((222, -14), (378, 14)):
        s += f'<g transform="rotate({rot} {cx} 240)">' + f'<rect x="{cx - 14}" y="240" width="28" height="86" rx="14" fill="{darken(a, .15)}"/>' \
             f'<ellipse cx="{cx}" cy="226" rx="46" ry="52" fill="{bud}"/><circle cx="{cx}" cy="226" r="16" fill="{b}" opacity=".9"/>' \
             f'<ellipse cx="{cx - 16}" cy="204" rx="14" ry="20" fill="#fff" opacity=".28"/></g>'
    return s, "floor"


def speaker(cv, p):
    a, b = p["a"], p["b"]
    body = cv.lin(lighten(a, .2), darken(a, .35))
    dots = cv.pattern_dots(darken(a, .55), 15, 3.4)
    s = f'<path d="M205 222 C205 150 395 150 395 222" fill="none" stroke="{darken(a, .4)}" stroke-width="12" stroke-linecap="round"/>'
    s += rr(110, 220, 380, 190, 92, body)
    s += rr(150, 246, 300, 138, 52, dots)
    s += rr(110, 292, 38, 46, 14, b) + rr(452, 292, 38, 46, 14, b)
    s += f'<circle cx="300" cy="440" r="8" fill="{b}"/>' + gloss("M140 246 Q300 214 460 246 Q300 232 140 270 Z", .22)
    return s, "floor"


def band(cv, p):
    a, b = p["a"], p["b"]
    strap = cv.lin(lighten(a, .15), darken(a, .25), 1, 0, 0, 0)
    face = cv.lin("#20263f", "#070a18")
    s = rr(252, 70, 96, 470, 30, strap)
    for y in (110, 150, 470, 505):
        s += f'<circle cx="300" cy="{y}" r="5" fill="{darken(a, .45)}"/>'
    s += rr(222, 200, 156, 200, 46, darken(a, .5)) + rr(234, 212, 132, 176, 36, face)
    s += f'<text x="300" y="276" text-anchor="middle" font-family="Arial,sans-serif" font-weight="700" font-size="44" fill="#fff">7:42</text>'
    s += f'<path d="M256 330 q14 -30 28 0 t28 0 t28 0" fill="none" stroke="{b}" stroke-width="7" stroke-linecap="round"/>'
    s += gloss("M242 222 Q250 216 310 218 Q262 234 252 290 Z", .16)
    return s, "floor"


def powerbank(cv, p):
    a, b = p["a"], p["b"]
    body = cv.lin(lighten(a, .2), darken(a, .35), 0, 0, 1, 1)
    s = f'<g transform="rotate(-6 300 300)">' + rr(180, 120, 240, 350, 40, body)
    s += rr(214, 142, 60, 16, 5, "#10132a") + rr(290, 142, 40, 16, 5, "#10132a") + rr(344, 142, 40, 16, 5, "#10132a")
    for i in range(4):
        s += f'<circle cx="{232 + i * 45}" cy="212" r="9" fill="{b if i < 3 else darken(b, .4)}"/>'
    s += rr(214, 270, 172, 8, 4, "#fff", 'opacity=".55"') + rr(214, 294, 120, 8, 4, "#fff", 'opacity=".35"')
    s += f'<text x="214" y="400" font-family="Arial,sans-serif" font-weight="800" font-size="44" fill="#fff" opacity=".9">20K</text>'
    s += gloss("M200 150 Q210 132 262 132 Q212 160 206 300 Z", .3) + "</g>"
    return s, "floor"


def charger(cv, p):
    a, b = p["a"], p["b"]
    body = cv.lin(lighten(a, .22), darken(a, .25), 0, 0, 1, 1)
    s = rr(262, 395, 18, 54, 4, "#b9bec9") + rr(320, 395, 18, 54, 4, "#b9bec9")
    s += rr(200, 160, 200, 250, 36, body) + rr(256, 196, 88, 22, 11, "#0e1126")
    s += f'<path d="M262 207 h76" stroke="{b}" stroke-width="4" stroke-linecap="round"/>'
    s += f'<text x="300" y="320" text-anchor="middle" font-family="Arial,sans-serif" font-weight="800" font-size="52" fill="#fff">33W</text>'
    s += gloss("M214 180 Q220 168 262 168 Q222 186 218 300 Z", .3)
    return s, "floor"


def mouse(cv, p):
    a, b = p["a"], p["b"]
    body = cv.lin(lighten(a, .25), darken(a, .3), 0, 0, 1, 1)
    s = f'<path d="M212 220 Q214 118 300 112 Q386 118 388 220 L402 392 Q402 500 300 506 Q198 500 198 392 Z" fill="{body}"/>'
    s += f'<path d="M300 112 V270" stroke="{darken(a, .4)}" stroke-width="4"/><path d="M212 270 Q300 290 388 270" fill="none" stroke="{darken(a, .4)}" stroke-width="4"/>'
    s += rr(288, 176, 24, 56, 12, b) + f'<circle cx="300" cy="420" r="16" fill="{darken(a, .45)}"/>'
    s += gloss("M226 214 Q232 140 290 128 Q246 170 244 330 Z", .28)
    return s, "floor"


def _shirt_body(cv, p, path, collar=False, buttons=0, neck=None, long_tail=False):
    a, b = p["a"], p["b"]
    fab = cv.lin(lighten(a, .14), darken(a, .2), 0, 0, 1, 1)
    s = f'<path d="{path}" fill="{fab}"/>'
    s += f'<path d="{path}" fill="none" stroke="{darken(a, .28)}" stroke-width="3" stroke-linejoin="round"/>'
    if neck:
        s += f'<path d="{neck}" fill="{darken(a, .38)}"/>'
    if collar:
        s += f'<path d="M265 118 L300 190 L248 160 Z" fill="{lighten(a, .12)}" stroke="{darken(a, .28)}" stroke-width="3"/><path d="M335 118 L300 190 L352 160 Z" fill="{lighten(a, .12)}" stroke="{darken(a, .28)}" stroke-width="3"/>'
    if buttons:
        s += f'<path d="M300 190 V{190 + buttons * 62}" stroke="{darken(a, .28)}" stroke-width="3"/>'
        for i in range(buttons):
            s += f'<circle cx="300" cy="{222 + i * 62}" r="6" fill="{b}"/>'
    return s


def shirt(cv, p):
    path = "M205 135 L265 118 Q300 150 335 118 L395 135 L505 235 L452 292 L412 258 L412 492 Q300 512 188 492 L188 258 L148 292 L95 235 Z"
    return _shirt_body(cv, p, path, collar=True, buttons=5), "drop"


def tshirt(cv, p):
    path = "M215 140 Q300 205 385 140 L495 205 L445 292 L408 262 L408 482 Q300 500 192 482 L192 262 L155 292 L105 205 Z"
    return _shirt_body(cv, p, path, neck="M236 143 Q300 205 364 143 Q300 176 236 143 Z"), "drop"


def kurta(cv, p):
    path = "M215 118 L265 106 Q300 138 335 106 L385 118 L482 222 L440 288 L402 256 L410 528 L352 528 L300 506 L248 528 L190 528 L198 256 L160 288 L118 222 Z"
    s = _shirt_body(cv, p, path, buttons=3)
    s = s.replace('M300 190 V376', 'M300 140 V300')
    s += f'<path d="M265 106 Q300 138 335 106 L322 124 Q300 150 278 124 Z" fill="{lighten(p["a"], .15)}"/>'
    s += f'<path d="M232 380 H370" stroke="{p["b"]}" stroke-width="3" stroke-dasharray="6 6" opacity=".7"/>'
    return s, "drop"


def jeans(cv, p):
    a, b = p["a"], p["b"]
    fab = cv.lin(lighten(a, .12), darken(a, .25), 0, 0, 1, 1)
    path = "M192 78 L408 78 L424 150 L398 526 L316 526 L300 238 L284 526 L202 526 L176 150 Z"
    s = f'<path d="{path}" fill="{fab}" stroke="{darken(a, .3)}" stroke-width="3" stroke-linejoin="round"/>'
    s += rr(192, 78, 216, 44, 4, darken(a, .12)) + f'<circle cx="300" cy="100" r="8" fill="{b}"/>'
    s += f'<path d="M300 122 V238" stroke="{darken(a, .38)}" stroke-width="3"/><path d="M212 130 Q240 190 276 176" fill="none" stroke="{b}" stroke-width="3" stroke-dasharray="7 5"/>'
    s += f'<path d="M388 130 Q360 190 324 176" fill="none" stroke="{b}" stroke-width="3" stroke-dasharray="7 5"/>'
    s += f'<path d="M222 300 L228 520 M378 300 L372 520" stroke="{lighten(a, .3)}" stroke-width="12" opacity=".22"/>'
    return s, "drop"


def hoodie(cv, p, zip_=False):
    a, b = p["a"], p["b"]
    fab = cv.lin(lighten(a, .14), darken(a, .24), 0, 0, 1, 1)
    path = "M198 168 Q300 130 402 168 L474 214 L510 408 L452 420 L424 306 L424 488 Q300 512 176 488 L176 306 L148 420 L90 408 L126 214 Z"
    s = f'<path d="{path}" fill="{fab}" stroke="{darken(a, .3)}" stroke-width="3" stroke-linejoin="round"/>'
    s += f'<path d="M214 170 Q208 78 300 78 Q392 78 386 170 Q300 214 214 170 Z" fill="{lighten(a, .08)}" stroke="{darken(a, .3)}" stroke-width="3"/>'
    s += f'<path d="M244 168 Q300 196 356 168 Q352 112 300 108 Q248 112 244 168 Z" fill="{darken(a, .5)}"/>'
    if zip_:
        s += f'<path d="M300 198 V486" stroke="{b}" stroke-width="6" stroke-dasharray="3 5"/>' + rr(292, 192, 16, 28, 5, b)
        s += f'<path d="M224 360 h60" stroke="{darken(a, .35)}" stroke-width="4" stroke-linecap="round"/>'
    else:
        s += f'<path d="M274 198 L270 290 M326 198 L330 290" stroke="{lighten(a, .55)}" stroke-width="6" stroke-linecap="round"/>'
        s += f'<path d="M222 388 L378 388 L396 458 L204 458 Z" fill="{darken(a, .1)}" stroke="{darken(a, .3)}" stroke-width="3"/>'
    return s, "drop"


def jacket(cv, p):
    return hoodie(cv, p, zip_=True)


def sneaker(cv, p, style="run"):
    a, b = p["a"], p["b"]
    up = cv.lin(lighten(a, .22), darken(a, .25), 0, 0, 1, 1)
    sole = cv.lin("#ffffff", "#c9ccd6")
    s = f'<path d="M92 420 Q92 396 112 396 L520 396 Q540 400 540 420 L538 440 Q536 456 516 456 L118 456 Q92 456 92 430 Z" fill="{sole}" stroke="#a7acba" stroke-width="2"/>'
    s += f'<path d="M104 436 H528" stroke="{b}" stroke-width="7" stroke-linecap="round"/>'
    s += f'<path d="M108 396 L106 300 Q108 252 154 244 L248 238 Q290 216 330 256 L410 302 Q496 312 530 380 L530 396 Z" fill="{up}" stroke="{darken(a, .32)}" stroke-width="3" stroke-linejoin="round"/>'
    s += f'<path d="M154 244 Q160 190 214 186 L250 238 Z" fill="{darken(a, .12)}" stroke="{darken(a, .32)}" stroke-width="3"/>'
    for i, (x, y) in enumerate(((280, 262), (322, 286), (364, 306))):
        s += f'<rect x="{x - 4}" y="{y - 20}" width="46" height="12" rx="6" fill="#fff" opacity=".92" transform="rotate(32 {x} {y})"/>'
    if style == "run":
        s += f'<path d="M126 372 Q250 340 400 372 Q470 384 520 388" fill="none" stroke="{b}" stroke-width="11" stroke-linecap="round"/>'
        s += f'<path d="M150 300 q40 -22 84 -14" fill="none" stroke="#fff" stroke-width="3" opacity=".55" stroke-dasharray="3 7"/>'
        s += gloss("M130 262 Q170 250 226 250 Q168 270 146 322 Z", .22)
    else:
        s += f'<path d="M110 398 L530 398" stroke="#fff" stroke-width="12"/>'
        s += f'<rect x="102" y="404" width="440" height="10" fill="{b}"/><circle cx="182" cy="330" r="18" fill="#fff" opacity=".9"/><circle cx="182" cy="330" r="9" fill="{b}"/>'
    return s, "floor"


def slide(cv, p):
    a, b = p["a"], p["b"]
    sole = cv.lin(lighten(a, .1), darken(a, .35))
    st = cv.lin(lighten(b, .15), darken(b, .2))
    s = f'<path d="M96 420 Q96 392 130 388 L470 372 Q528 372 530 408 Q528 444 470 446 L130 450 Q96 450 96 420 Z" fill="{sole}"/>'
    s += f'<path d="M96 424 Q96 452 130 456 L470 452 Q526 452 530 414" fill="none" stroke="{darken(a, .5)}" stroke-width="10"/>'
    s += f'<path d="M168 392 Q214 264 330 262 Q430 266 470 380 L440 384 Q408 304 330 304 Q250 306 206 392 Z" fill="{st}"/>'
    s += f'<path d="M190 330 Q300 300 432 340" fill="none" stroke="#fff" stroke-width="3" opacity=".4"/>'
    return s, "floor"


def formal_shoe(cv, p):
    a, b = p["a"], p["b"]
    up = cv.lin(lighten(a, .3), darken(a, .3), 0, 0, 1, 1)
    s = f'<path d="M96 430 L520 430 Q540 430 540 446 Q540 462 520 462 L108 462 Q92 462 92 446 Z" fill="#14121a"/>'
    s += f'<rect x="96" y="414" width="76" height="20" rx="4" fill="{darken(a, .55)}"/>'
    s += f'<path d="M104 420 L100 300 Q104 262 150 258 L246 252 Q290 232 330 262 L420 320 Q510 336 540 396 Q540 424 516 424 Z" fill="{up}" stroke="{darken(a, .4)}" stroke-width="3" stroke-linejoin="round"/>'
    s += f'<path d="M420 322 Q470 324 508 360" fill="none" stroke="{darken(a, .4)}" stroke-width="3"/><path d="M430 340 Q470 344 500 372" fill="none" stroke="{darken(a, .35)}" stroke-width="2" stroke-dasharray="4 4"/>'
    for i in range(4):
        s += f'<ellipse cx="{286 + i * 36}" cy="{274 + i * 16}" rx="16" ry="6" fill="{darken(a, .55)}" transform="rotate(28 {286 + i * 36} {274 + i * 16})"/>'
    s += gloss("M130 280 Q168 270 226 268 Q162 292 140 340 Z", .3)
    return s, "floor"


def bottle(cv, p, slim=False):
    a, b = p["a"], p["b"]
    x0, x1 = (240, 360) if slim else (222, 378)
    body = cv.lin(lighten(a, .35), darken(a, .3), 0, 0, 1, 0, mid=a)
    cap = cv.lin(lighten(b, .1), darken(b, .35), 0, 0, 1, 0)
    s = rr(x0 + 14, 70, x1 - x0 - 28, 34, 10, cap) + rr(x0 + 22, 100, x1 - x0 - 44, 24, 6, darken(a, .3))
    s += f'<path d="M{x0} 160 Q{x0} 122 {x0 + 30} 122 H{x1 - 30} Q{x1} 122 {x1} 160 V480 Q{x1} 510 {x1 - 30} 510 H{x0 + 30} Q{x0} 510 {x0} 480 Z" fill="{body}"/>'
    s += f'<rect x="{x0}" y="300" width="{x1 - x0}" height="64" fill="{b}" opacity=".92"/><rect x="{x0}" y="372" width="{x1 - x0}" height="6" fill="{b}" opacity=".5"/>'
    s += f'<rect x="{x0 + 14}" y="150" width="14" height="330" rx="7" fill="#fff" opacity=".35"/>'
    return s, "floor"


def pan(cv, p):
    a, b = p["a"], p["b"]
    rim = cv.lin(lighten(a, .2), darken(a, .5), 0, 0, 1, 1)
    inner = cv.rad(lighten(a, .12), darken(a, .55), .45, .35, .8)
    handle = cv.lin(lighten(b, .1), darken(b, .4), 0, 0, 0, 1)
    s = f'<path d="M430 300 L570 262 Q590 258 590 280 Q590 300 570 306 L430 346 Z" fill="{handle}"/>'
    s += f'<ellipse cx="270" cy="330" rx="200" ry="150" fill="{rim}"/><ellipse cx="270" cy="326" rx="176" ry="128" fill="{inner}"/>'
    s += f'<ellipse cx="270" cy="326" rx="120" ry="82" fill="none" stroke="#fff" stroke-width="2" opacity=".14"/>'
    s += f'<path d="M120 270 Q170 220 250 212" fill="none" stroke="#fff" stroke-width="8" opacity=".25" stroke-linecap="round"/>'
    return s, "floor"


def kettle(cv, p):
    a, b = p["a"], p["b"]
    body = cv.lin(lighten(a, .35), darken(a, .3), 0, 0, 1, 0, mid=a)
    s = f'<path d="M190 250 Q110 220 98 150 L124 140 Q146 196 214 214 Z" fill="{darken(a, .15)}"/>'
    s += f'<path d="M412 190 Q520 190 504 330 Q494 404 408 412" fill="none" stroke="{b}" stroke-width="26" stroke-linecap="round"/>'
    s += f'<path d="M180 470 L212 232 Q300 196 388 232 L420 470 Q300 506 180 470 Z" fill="{body}"/>'
    s += f'<ellipse cx="300" cy="226" rx="92" ry="26" fill="{lighten(a, .15)}"/><rect x="284" y="178" width="32" height="40" rx="12" fill="{b}"/>'
    s += f'<rect x="170" y="466" width="260" height="34" rx="14" fill="{darken(a, .55)}"/><circle cx="300" cy="483" r="7" fill="#7cf08a"/>'
    s += f'<rect x="226" y="262" width="12" height="190" rx="6" fill="#fff" opacity=".35"/>'
    return s, "floor"


def mugs(cv, p):
    a, b = p["a"], p["b"]
    s = ""
    for dx, dy, col in ((0, 20, a), (150, -10, b)):
        body = cv.lin(lighten(col, .3), darken(col, .25), 0, 0, 1, 0)
        s += f'<path d="M{346 + dx - 150} {260 + dy} q70 -6 70 60 q0 70 -70 64" fill="none" stroke="{darken(col, .2)}" stroke-width="20" stroke-linecap="round" transform="translate(30 0)"/>'
        s += f'<path d="M{130 + dx} {200 + dy} H{300 + dx} V{380 + dy} Q{300 + dx} {430 + dy} {250 + dx} {430 + dy} H{180 + dx} Q{130 + dx} {430 + dy} {130 + dx} {380 + dy} Z" fill="{body}"/>'
        s += f'<ellipse cx="{215 + dx}" cy="{200 + dy}" rx="85" ry="16" fill="{darken(col, .5)}"/><ellipse cx="{215 + dx}" cy="{204 + dy}" rx="76" ry="11" fill="#4a2c1d" opacity=".9"/>'
        s += f'<rect x="{146 + dx}" y="{232 + dy}" width="12" height="150" rx="6" fill="#fff" opacity=".4"/>'
    return s, "floor"


def lamp(cv, p):
    a, b = p["a"], p["b"]
    metal = cv.lin(lighten(a, .3), darken(a, .35), 1, 0, 0, 0)
    s = f'<path d="M330 214 L220 520 L480 520 Z" fill="{b}" opacity=".13"/>'
    s += rr(190, 484, 190, 28, 14, darken(a, .3))
    s += f'<path d="M286 486 L236 300 L340 160" fill="none" stroke="{metal}" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>'
    s += f'<circle cx="236" cy="300" r="14" fill="{b}"/><circle cx="286" cy="486" r="14" fill="{darken(a, .4)}"/>'
    s += f'<g transform="rotate(32 340 160)"><path d="M290 150 Q290 100 340 98 Q390 100 390 150 L400 200 L280 200 Z" fill="{metal}"/><ellipse cx="340" cy="200" rx="60" ry="10" fill="#fff6c9"/></g>'
    return s, "floor"


def bedsheet(cv, p):
    a, b = p["a"], p["b"]
    s = ""
    for i, (y, col) in enumerate(((350, darken(a, .08)), (270, a), (190, lighten(a, .12)))):
        g = cv.lin(lighten(col, .12), darken(col, .18), 0, 0, 0, 1)
        s += rr(110 + i * 12, y, 380 - i * 24, 132, 22, g)
        s += f'<path d="M{124 + i * 12} {y + 100} H{476 - i * 12}" stroke="{b}" stroke-width="6" opacity=".75"/>'
        s += f'<path d="M{124 + i * 12} {y + 20} Q300 {y - 6} {476 - i * 12} {y + 20}" fill="none" stroke="#fff" stroke-width="3" opacity=".3"/>'
    return s, "drop"


def jars(cv, p):
    a, b = p["a"], p["b"]
    s = ""
    for x, h, lid in ((100, 230, b), (230, 290, a), (370, 340, b)):
        top = 510 - h
        glass = cv.lin("#ffffff", lighten(a, .55), 0, 0, 1, 0)
        s += f'<rect x="{x}" y="{top}" width="130" height="{h}" rx="22" fill="{glass}" opacity=".78" stroke="#c6cbe0" stroke-width="3"/>'
        s += f'<rect x="{x + 6}" y="{top + h * .45}" width="118" height="{h * .55 - 6}" rx="18" fill="{lighten(a, .2)}" opacity=".7"/>'
        s += rr(x - 4, top - 30, 138, 38, 10, lid) + f'<rect x="{x + 16}" y="{top + 18}" width="12" height="{h - 50}" rx="6" fill="#fff" opacity=".6"/>'
    return s, "floor"


def tube(cv, p):
    a, b = p["a"], p["b"]
    body = cv.lin(lighten(a, .35), darken(a, .15), 0, 0, 1, 0, mid=a)
    cap = cv.lin(lighten(b, .2), darken(b, .3), 0, 0, 1, 0)
    s = f'<path d="M232 130 L368 130 L354 424 L246 424 Z" fill="{body}"/>'
    s += rr(228, 96, 144, 40, 6, darken(a, .08)) + "".join(f'<path d="M{236 + i * 14} 100 v32" stroke="{darken(a, .25)}" stroke-width="2" opacity=".6"/>' for i in range(10))
    s += rr(246, 420, 108, 78, 14, cap)
    s += f'<circle cx="300" cy="262" r="40" fill="{b}"/>' + "".join(
        f'<path d="M{300 + 52 * math.cos(math.radians(t)):.1f} {262 + 52 * math.sin(math.radians(t)):.1f} L{300 + 66 * math.cos(math.radians(t)):.1f} {262 + 66 * math.sin(math.radians(t)):.1f}" stroke="{b}" stroke-width="6" stroke-linecap="round"/>' for t in range(0, 360, 45))
    s += f'<rect x="254" y="150" width="12" height="250" rx="6" fill="#fff" opacity=".4"/>'
    return s, "floor"


def pump_bottle(cv, p):
    a, b = p["a"], p["b"]
    body = cv.lin(lighten(a, .35), darken(a, .15), 0, 0, 1, 0, mid=a)
    s = rr(284, 120, 32, 70, 8, darken(b, .1)) + rr(262, 100, 124, 28, 12, b) + rr(246, 188, 108, 34, 8, darken(b, .15))
    s += f'<path d="M226 270 Q226 222 270 222 H330 Q374 222 374 270 V470 Q374 510 334 510 H266 Q226 510 226 470 Z" fill="{body}"/>'
    s += rr(226, 330, 148, 110, 10, "#fff", 'opacity=".9"') + f'<circle cx="300" cy="372" r="18" fill="{b}"/><rect x="254" y="402" width="92" height="8" rx="4" fill="{darken(a, .25)}"/><rect x="266" y="418" width="68" height="6" rx="3" fill="{darken(a, .1)}" opacity=".6"/>'
    s += f'<rect x="240" y="244" width="12" height="230" rx="6" fill="#fff" opacity=".4"/>'
    return s, "floor"


def dropper(cv, p):
    a, b = p["a"], p["b"]
    glass = cv.lin(lighten(a, .3), darken(a, .35), 0, 0, 1, 0, mid=a)
    s = f'<path d="M286 120 Q286 70 300 66 Q314 70 314 120 V196 H286 Z" fill="{darken(b, .1)}"/>'
    s += f'<path d="M250 112 Q250 76 300 70 Q350 76 350 112 L342 196 H258 Z" fill="{b}"/>' + rr(246, 190, 108, 40, 8, darken(b, .4))
    s += f'<path d="M226 300 Q226 240 262 232 H338 Q374 240 374 300 V462 Q374 506 332 506 H268 Q226 506 226 462 Z" fill="{glass}"/>'
    s += rr(240, 340, 120, 100, 8, "#fff", 'opacity=".92"') + f'<text x="300" y="382" text-anchor="middle" font-family="Arial,sans-serif" font-weight="800" font-size="30" fill="{darken(a, .45)}">C+</text>'
    s += f'<rect x="256" y="404" width="88" height="6" rx="3" fill="{darken(a, .2)}" opacity=".6"/><rect x="242" y="260" width="12" height="220" rx="6" fill="#fff" opacity=".4"/>'
    return s, "floor"


def trimmer(cv, p):
    a, b = p["a"], p["b"]
    body = cv.lin(lighten(a, .25), darken(a, .35), 0, 0, 1, 0)
    s = '<g transform="rotate(-10 300 300)">' + rr(250, 160, 100, 350, 44, body)
    s += rr(236, 96, 128, 78, 16, "#c8ccd8") + "".join(f'<rect x="{244 + i * 11}" y="80" width="6" height="30" rx="2" fill="#8d93a6"/>' for i in range(11))
    s += rr(236, 150, 128, 28, 10, b) + f'<circle cx="300" cy="260" r="20" fill="{darken(a, .5)}"/><circle cx="300" cy="260" r="8" fill="{b}"/>'
    s += rr(284, 320, 32, 8, 4, "#fff", 'opacity=".5"') + rr(284, 340, 32, 8, 4, "#fff", 'opacity=".3"')
    s += gloss("M264 190 Q268 172 292 170 Q272 220 270 360 Z", .28) + "</g>"
    return s, "floor"


def shampoo(cv, p):
    a, b = p["a"], p["b"]
    body = cv.lin(lighten(a, .35), darken(a, .2), 0, 0, 1, 0, mid=a)
    s = rr(256, 120, 88, 70, 14, b) + rr(250, 176, 100, 26, 6, darken(b, .25)) + f'<circle cx="300" cy="148" r="6" fill="{darken(b, .45)}"/>'
    s += f'<path d="M214 292 Q214 214 262 204 H338 Q386 214 386 292 V462 Q386 510 338 510 H262 Q214 510 214 462 Z" fill="{body}"/>'
    s += rr(214, 316, 172, 130, 12, "#fff", 'opacity=".92"')
    s += f'<path d="M300 424 Q256 400 270 352 Q316 360 300 424 Z" fill="{darken(a, .1)}"/><path d="M300 424 Q338 396 328 366" fill="none" stroke="{b}" stroke-width="5" stroke-linecap="round"/>'
    s += f'<rect x="232" y="236" width="12" height="238" rx="6" fill="#fff" opacity=".4"/>'
    return s, "floor"


def yoga_mat(cv, p):
    a, b = p["a"], p["b"]
    body = cv.lin(lighten(a, .3), darken(a, .25), 0, 0, 0, 1)
    s = f'<path d="M150 360 L520 350 L560 420 L170 440 Z" fill="{darken(a, .1)}" opacity=".9"/>'
    s += rr(150, 210, 330, 170, 20, body)
    s += f'<ellipse cx="150" cy="295" rx="48" ry="85" fill="{lighten(a, .2)}"/>'
    for r in (74, 56, 40, 24, 10):
        s += f'<ellipse cx="150" cy="295" rx="{r * .56:.0f}" ry="{r:.0f}" fill="none" stroke="{darken(a, .3)}" stroke-width="3"/>'
    s += rr(250, 204, 26, 182, 6, b) + rr(380, 204, 26, 182, 6, b)
    s += rr(180, 226, 290, 10, 5, "#fff", 'opacity=".35"')
    return s, "floor"


def dumbbell(cv, p):
    a, b = p["a"], p["b"]
    head = cv.lin(lighten(a, .2), darken(a, .5), 0, 0, 1, 1)
    s = rr(180, 280, 240, 40, 12, "#b8bccb") + "".join(f'<path d="M{236 + i * 8} 282 v36" stroke="#8d92a6" stroke-width="2"/>' for i in range(14))
    for x in (96, 392):
        s += f'<path d="M{x + 18} 190 H{x + 92} L{x + 112} 300 L{x + 92} 410 H{x + 18} L{x - 2} 300 Z" fill="{head}"/><path d="M{x + 18} 190 H{x + 92} L{x + 100} 220 H{x + 10} Z" fill="#fff" opacity=".22"/>'
        s += f'<circle cx="{x + 55}" cy="300" r="22" fill="{b}"/>'
    return s, "floor"


def rope(cv, p):
    a, b = p["a"], p["b"]
    s = f'<path d="M196 430 C130 100 470 100 404 430" fill="none" stroke="{a}" stroke-width="9" stroke-linecap="round"/>'
    s += f'<path d="M196 430 C250 250 350 250 404 430" fill="none" stroke="{lighten(a, .3)}" stroke-width="5" stroke-linecap="round" stroke-dasharray="2 9" opacity=".8"/>'
    for x in (160, 380):
        g = cv.lin(lighten(b, .2), darken(b, .35), 1, 0, 0, 0)
        s += rr(x, 420, 60, 120, 28, g) + rr(x + 6, 420, 48, 28, 12, darken(b, .45)) + f'<rect x="{x + 14}" y="460" width="10" height="64" rx="5" fill="#fff" opacity=".4"/>'
    return s, "floor"


def bands(cv, p):
    s = ""
    cols = [p["a"], p["b"], p.get("c", "#f4b400"), "#e8604c", "#1f2a44"]
    for i, c in enumerate(cols):
        y = 170 + i * 66
        s += f'<ellipse cx="300" cy="{y}" rx="190" ry="54" fill="none" stroke="{darken(c, .25)}" stroke-width="30"/>'
        s += f'<ellipse cx="300" cy="{y - 3}" rx="190" ry="54" fill="none" stroke="{c}" stroke-width="22"/>'
        s += f'<path d="M150 {y - 24} Q240 {y - 48} 330 {y - 46}" fill="none" stroke="#fff" stroke-width="4" opacity=".35" stroke-linecap="round"/>'
    return s, "floor"


def football(cv, p):
    a, b = p["a"], p["b"]
    ball = cv.rad("#ffffff", "#c7cad6", .38, .32, .75)
    s = f'<circle cx="300" cy="300" r="196" fill="{ball}" stroke="#aeb3c4" stroke-width="3"/>'
    pent = lambda cx, cy, r, rot: " ".join(f"{cx + r * math.cos(math.radians(rot + 72 * k)):.1f},{cy + r * math.sin(math.radians(rot + 72 * k)):.1f}" for k in range(5))
    s += f'<polygon points="{pent(300, 300, 62, -90)}" fill="{a}"/>'
    for k in range(5):
        ang = math.radians(-90 + 72 * k)
        x1, y1 = 300 + 62 * math.cos(ang), 300 + 62 * math.sin(ang)
        x2, y2 = 300 + 128 * math.cos(ang), 300 + 128 * math.sin(ang)
        s += f'<path d="M{x1:.1f} {y1:.1f} L{x2:.1f} {y2:.1f}" stroke="{darken(a, .1)}" stroke-width="4"/>'
        s += f'<polygon points="{pent(300 + 168 * math.cos(ang), 300 + 168 * math.sin(ang), 46, -90 + 72 * k + 36)}" fill="{b}" opacity=".95"/>'
    s += '<ellipse cx="236" cy="206" rx="64" ry="36" fill="#fff" opacity=".45" transform="rotate(-30 236 206)"/>'
    return s, "floor"


def foam_roller(cv, p):
    a, b = p["a"], p["b"]
    body = cv.lin(lighten(a, .25), darken(a, .35), 0, 0, 0, 1)
    s = rr(110, 214, 380, 176, 52, body)
    s += "".join(f'<rect x="{150 + i * 36}" y="214" width="14" height="176" fill="{darken(a, .2)}" opacity=".5"/>' for i in range(9))
    s += f'<ellipse cx="116" cy="302" rx="44" ry="88" fill="{lighten(a, .12)}"/><ellipse cx="116" cy="302" rx="22" ry="44" fill="{darken(a, .35)}"/>'
    s += rr(130, 230, 340, 12, 6, "#fff", 'opacity=".3"') + rr(250, 214, 18, 176, 4, b, 'opacity=".9"')
    return s, "floor"


def notebook(cv, p):
    a, b = p["a"], p["b"]
    cover = cv.lin(lighten(a, .18), darken(a, .22), 0, 0, 1, 0)
    s = '<g transform="rotate(-5 300 300)">' + rr(186, 80, 232, 440, 14, "#f6f1e4") + rr(180, 84, 232, 440, 14, cover)
    s += rr(180, 84, 26, 440, 10, darken(a, .3)) + rr(352, 84, 26, 440, 4, b, 'opacity=".95"')
    s += rr(228, 150, 100, 70, 8, "#fff", 'opacity=".9"') + rr(242, 168, 70, 8, 4, darken(a, .3)) + rr(242, 188, 50, 8, 4, darken(a, .1), 'opacity=".5"')
    s += "".join(f'<circle cx="{236 + (i % 6) * 18}" cy="{300 + (i // 6) * 18}" r="2.5" fill="#fff" opacity=".5"/>' for i in range(36))
    s += gloss("M196 100 Q200 90 230 90 Q204 120 204 300 Z", .2) + "</g>"
    return s, "drop"


def pens(cv, p):
    cols = [p["a"], p["b"], p.get("c", "#e8604c"), "#16a085", "#f4b400"]
    s = ""
    for i, c in enumerate(cols):
        rot = -34 + i * 17
        g = cv.lin(lighten(c, .25), darken(c, .3), 0, 0, 1, 0)
        s += f'<g transform="rotate({rot} 300 540)">' + rr(280, 140, 40, 330, 20, g) + f'<path d="M280 150 L300 88 L320 150 Z" fill="{darken(c, .45)}"/><circle cx="300" cy="88" r="5" fill="#222"/>' \
             f'<rect x="286" y="190" width="6" height="200" rx="3" fill="#fff" opacity=".45"/><rect x="280" y="420" width="40" height="14" fill="{darken(c, .4)}"/></g>'
    return s, "floor"


def planner(cv, p):
    a, b = p["a"], p["b"]
    s = rr(140, 100, 320, 410, 16, "#fffdf6", 'stroke="#d9d3c0" stroke-width="2"')
    s += rr(140, 100, 320, 70, 16, a) + rr(140, 140, 320, 30, 0, a)
    s += f'<text x="170" y="150" font-family="Arial,sans-serif" font-weight="800" font-size="30" fill="#fff">WEEK</text>'
    for i in range(7):
        y = 206 + i * 44
        s += f'<path d="M170 {y} H430" stroke="#d9d3c0" stroke-width="2"/><rect x="170" y="{y - 26}" width="14" height="14" rx="3" fill="{b if i % 3 == 0 else "#e7e2d0"}"/>'
    s += "".join(f'<rect x="{196 + i * 56}" y="86" width="30" height="24" rx="6" fill="{darken(a, .25)}"/>' for i in range(4))
    return s, "drop"


def book(cv, p):
    a, b = p["a"], p["b"]
    cover = cv.lin(lighten(a, .18), darken(a, .3), 0, 0, 1, 1)
    s = '<g transform="rotate(4 300 300)">' + rr(206, 84, 218, 432, 8, "#f1ecdd")
    s += "".join(f'<path d="M408 {100 + i * 36} H424" stroke="#cfc8b3" stroke-width="2"/>' for i in range(12))
    s += rr(194, 80, 222, 432, 8, cover) + rr(194, 80, 22, 432, 6, darken(a, .35))
    s += f'<circle cx="305" cy="214" r="46" fill="none" stroke="{b}" stroke-width="5"/><path d="M270 230 Q305 170 340 230" fill="none" stroke="{b}" stroke-width="5"/>'
    s += f'<text x="305" y="330" text-anchor="middle" font-family="Georgia,serif" font-weight="700" font-size="30" fill="#fff">THE QUIET</text><text x="305" y="368" text-anchor="middle" font-family="Georgia,serif" font-weight="700" font-size="30" fill="#fff">LEDGER</text>'
    s += rr(250, 450, 110, 6, 3, b) + "</g>"
    return s, "drop"


def highlighters(cv, p):
    cols = [p["a"], p["b"], p.get("c", "#9be564"), "#ffd166", "#ef8fb0", "#7ad7f0"]
    s = ""
    for i, c in enumerate(cols):
        x = 112 + i * 62
        g = cv.lin(lighten(c, .2), darken(c, .2), 0, 0, 1, 0)
        s += rr(x, 190, 50, 280, 18, "#f1f2f8") + rr(x, 190, 50, 120, 12, g) + f'<path d="M{x + 8} 190 L{x + 14} 128 H{x + 36} L{x + 42} 190 Z" fill="{c}"/>'
        s += rr(x + 6, 470, 38, 30, 8, darken(c, .1)) + f'<rect x="{x + 10}" y="204" width="8" height="92" rx="4" fill="#fff" opacity=".45"/>'
    return s, "floor"


def backpack(cv, p, big=True):
    a, b = p["a"], p["b"]
    body = cv.lin(lighten(a, .2), darken(a, .3), 0, 0, 1, 1)
    s = f'<path d="M262 118 Q262 70 300 70 Q338 70 338 118" fill="none" stroke="{darken(a, .4)}" stroke-width="16" stroke-linecap="round"/>'
    s += f'<path d="M176 200 Q176 108 300 108 Q424 108 424 200 L446 468 Q448 512 404 512 H196 Q152 512 154 468 Z" fill="{body}"/>'
    s += rr(196, 330, 208, 150, 28, lighten(a, .08)) + f'<path d="M196 372 H404" stroke="{darken(a, .35)}" stroke-width="4"/>' + rr(282, 355, 36, 30, 8, b)
    s += f'<path d="M206 214 Q300 180 394 214" fill="none" stroke="{darken(a, .38)}" stroke-width="4"/><circle cx="300" cy="198" r="9" fill="{b}"/>'
    s += f'<path d="M158 262 Q122 330 150 440" fill="none" stroke="{darken(a, .45)}" stroke-width="22" stroke-linecap="round"/><path d="M442 262 Q478 330 450 440" fill="none" stroke="{darken(a, .45)}" stroke-width="22" stroke-linecap="round"/>'
    s += gloss("M196 160 Q210 124 270 120 Q214 150 206 300 Z", .26)
    return s, "floor"


def tote(cv, p):
    a, b = p["a"], p["b"]
    body = cv.lin(lighten(a, .2), darken(a, .2), 0, 0, 1, 1)
    s = f'<path d="M222 258 Q222 76 300 76 Q378 76 378 258" fill="none" stroke="{darken(a, .35)}" stroke-width="20" stroke-linecap="round"/>'
    s += f'<path d="M150 252 H450 L474 510 H126 Z" fill="{body}"/>'
    s += f'<path d="M150 252 H450" stroke="{darken(a, .3)}" stroke-width="6"/>' + rr(232, 330, 136, 100, 8, b, 'opacity=".92"')
    s += f'<text x="300" y="392" text-anchor="middle" font-family="Georgia,serif" font-weight="700" font-size="34" fill="#fff">carry</text>'
    s += f'<path d="M126 470 H474" stroke="{darken(a, .3)}" stroke-width="3" stroke-dasharray="8 6" opacity=".6"/>'
    return s, "drop"


def duffel(cv, p):
    a, b = p["a"], p["b"]
    body = cv.lin(lighten(a, .2), darken(a, .35), 0, 0, 0, 1)
    s = f'<path d="M200 270 Q210 110 300 110 Q390 110 400 270" fill="none" stroke="{darken(a, .4)}" stroke-width="18" stroke-linecap="round"/>'
    s += f'<path d="M150 330 Q300 560 450 330" fill="none" stroke="{darken(a, .5)}" stroke-width="16" stroke-linecap="round" opacity=".8" transform="translate(0 -40)"/>'
    s += rr(70, 250, 460, 220, 84, body) + f'<path d="M110 300 H490" stroke="{darken(a, .45)}" stroke-width="5"/><path d="M110 300 H490" stroke="{b}" stroke-width="2" stroke-dasharray="3 7"/>'
    s += rr(150, 356, 150, 90, 22, lighten(a, .06), f'stroke="{darken(a, .4)}" stroke-width="3"') + rr(440, 280, 60, 150, 26, darken(a, .25))
    s += f'<circle cx="360" cy="300" r="10" fill="{b}"/>' + gloss("M110 290 Q120 262 220 262 Q130 292 120 380 Z", .24)
    return s, "floor"


DRAW = {
    "headphones": headphones, "headphones_wired": lambda cv, p: headphones(cv, p, wired=True), "earbuds": earbuds, "speaker": speaker, "band": band,
    "powerbank": powerbank, "charger": charger, "mouse": mouse, "shirt": shirt, "tshirt": tshirt, "kurta": kurta, "jeans": jeans, "hoodie": hoodie,
    "jacket": jacket, "sneaker_run": sneaker, "sneaker_canvas": lambda cv, p: sneaker(cv, p, "canvas"), "slide": slide, "formal_shoe": formal_shoe,
    "bottle": bottle, "bottle_slim": lambda cv, p: bottle(cv, p, True), "pan": pan, "kettle": kettle, "mugs": mugs, "lamp": lamp, "bedsheet": bedsheet,
    "jars": jars, "tube": tube, "pump_bottle": pump_bottle, "dropper": dropper, "trimmer": trimmer, "shampoo": shampoo, "yoga_mat": yoga_mat,
    "dumbbell": dumbbell, "rope": rope, "bands": bands, "football": football, "foam_roller": foam_roller, "notebook": notebook, "pens": pens,
    "planner": planner, "book": book, "highlighters": highlighters, "backpack": backpack, "tote": tote, "duffel": duffel,
}
FOCAL = {"headphones": (170, 380), "headphones_wired": (170, 380), "earbuds": (300, 300), "speaker": (300, 310), "band": (300, 300), "powerbank": (300, 220), "charger": (300, 260),
         "mouse": (300, 250), "shirt": (300, 200), "tshirt": (300, 200), "kurta": (300, 220), "jeans": (300, 140), "hoodie": (300, 200), "jacket": (300, 260),
         "sneaker_run": (300, 340), "sneaker_canvas": (200, 330), "slide": (320, 320), "formal_shoe": (380, 340), "bottle": (300, 220), "bottle_slim": (300, 220), "pan": (300, 300),
         "kettle": (300, 260), "mugs": (230, 300), "lamp": (350, 200), "bedsheet": (300, 300), "jars": (300, 300), "tube": (300, 270), "pump_bottle": (300, 330), "dropper": (300, 360),
         "trimmer": (300, 180), "shampoo": (300, 330), "yoga_mat": (170, 295), "dumbbell": (150, 300), "rope": (300, 200), "bands": (300, 260), "football": (300, 300),
         "foam_roller": (300, 300), "notebook": (300, 220), "pens": (300, 160), "planner": (300, 200), "book": (305, 250), "highlighters": (300, 260), "backpack": (300, 400),
         "tote": (300, 380), "duffel": (300, 340)}


def render(kind: str, pal: dict, view: int, tint: str) -> str:
    cv = Canvas()
    body, shadow = DRAW[kind](cv, pal)
    if view == 2:
        bg = cv.lin("#0b1026", "#1f2c78", 0, 0, 1, 1)
        glow = cv.rad(lighten(tint, .1), "#0b1026", .5, .5, .55)
        scene = f'<rect width="600" height="600" fill="{bg}"/><circle cx="300" cy="300" r="270" fill="{glow}" opacity=".55"/>'
        obj = f'<g transform="translate(300 300) rotate(-9) scale(.9) translate(-300 -300)">{body}</g>'
    else:
        bg = cv.rad(lighten(tint, .78), tint, .5, .38, .85)
        scene = f'<rect width="600" height="600" fill="{bg}"/><ellipse cx="300" cy="560" rx="260" ry="26" fill="#fff" opacity=".35"/>'
        obj = body
    if shadow == "floor":
        scene += f'<ellipse cx="300" cy="530" rx="190" ry="20" fill="#0b1026" opacity="{.28 if view == 2 else .16}" filter="{cv.blur(11)}"/>'
        obj_el = f"<g>{obj}</g>"
    else:
        obj_el = f'<g filter="{cv.shadow()}">{obj}</g>'
    if view == 3:
        fx, fy = FOCAL.get(kind, (300, 300))
        vb = f"{max(0, min(300, fx - 150))} {max(0, min(300, fy - 150))} 300 300"
        obj_el = f'<g transform="translate({fx} {fy}) rotate(4) translate({-fx} {-fy})">{obj_el}</g>'
    else:
        vb = "0 0 600 600"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="600" height="600" role="img"><defs>{"".join(cv.defs)}</defs>{scene}{obj_el}</svg>')
