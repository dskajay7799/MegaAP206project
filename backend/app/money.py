"""Money helpers. All stored amounts are integer paise; the API also exposes rupee floats for the assistant's compatibility."""
from decimal import ROUND_HALF_UP, Decimal


def to_paise(rupees) -> int | None:
    if rupees is None or rupees == "":
        return None
    return int((Decimal(str(rupees)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_rupees(paise: int | None) -> float | None:
    return None if paise is None else paise / 100


def text(paise: int | None) -> str:
    if paise is None:
        return "Price not listed"
    r = paise / 100
    s = f"{int(r):,}" if paise % 100 == 0 else f"{r:,.2f}"
    # Indian digit grouping (12,34,567) to match how shoppers read prices
    whole, _, frac = s.partition(".")
    whole = whole.replace(",", "")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return "₹" + whole + ("." + frac if frac else "")
