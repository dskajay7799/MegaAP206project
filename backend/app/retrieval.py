"""Dependency-free BM25 index with light query normalisation.

Normalisation is deliberately conservative: equivalence synonyms (incl. a few Hinglish words), a stemmer, and typo
correction restricted to words that are NOT in the catalogue vocabulary (same first letter, edit distance <= 1-2).
Normalisation only widens *recall*; every answer is still composed from catalogue fields, never from similarity alone.
"""
import math
import re
from collections import Counter
from functools import lru_cache

from .nlu import GENERAL_STOP

STOP = frozenset("""a an the is are was of to for in on and or me my i you your do does did it its this that with at be
ka ki ke hai hain kya mein se ko chahiye dikhao batao bata show tell please pls what whats which how much many price cost
under below above less than upto within max budget rs inr sell have has there any available stock want need looking
already said also can could would get give find list suggest recommend options option about only ones one those these them
ok okay yes no instead more
cheap cheapest cheaper lowest highest rated rating ratings top best good nice great sasta sabse better accha achha kaun konsa
spec specs specification details detail feature features info information material size color colour""".split()) | GENERAL_STOP

# Colour words are recognised even when the catalogue stocks none (so "only black ones" is a constraint, not a topic).
COLOURS = frozenset("black white red blue green yellow grey beige navy brown pink orange purple maroon cream olive tan gold silver teal khaki".split())

# Equivalence synonyms (query and documents are normalised identically).
SYNONYMS = {
    "sneaker": ["shoe"], "sneakers": ["shoe"], "trainer": ["shoe"], "trainers": ["shoe"],
    "joota": ["shoe"], "jootey": ["shoe"], "joote": ["shoe"], "jute": ["shoe"],
    "tshirt": ["t", "shirt"], "tshirts": ["t", "shirt"], "tee": ["t", "shirt"], "tees": ["t", "shirt"],
    "colour": ["color"], "colours": ["color"], "gray": ["grey"],
    "paani": ["water"], "pani": ["water"],
    "kala": ["black"], "kali": ["black"], "safed": ["white"], "neela": ["blue"], "neeli": ["blue"],
    "lal": ["red"], "hara": ["green"], "peela": ["yellow"],
    # "noise cancelling" (highlights) and "noise cancellation" (spec label) must meet; so must the policy's "cancelled".
    "cancelling": ["cancel"], "canceling": ["cancel"], "cancelled": ["cancel"], "canceled": ["cancel"], "cancellation": ["cancel"], "cancellations": ["cancel"],
}


def _stem(t: str) -> str:
    return t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t


def _osa(a: str, b: str, limit: int) -> int:
    """Optimal-string-alignment distance (insert/delete/substitute/transpose), early exit above `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
        if min(cur) > limit:
            return limit + 1
    return prev[-1]


def correct(word: str, vocab) -> str:
    """Memoised wrapper: the vocabulary is a frozenset (its hash is cached), so repeated words cost a dict lookup instead of a vocabulary scan."""
    try:
        return _correct_cached(word, vocab)
    except TypeError:                       # an unhashable vocab (a plain set) still works, just uncached
        return _correct(word, vocab)


@lru_cache(maxsize=65536)
def _correct_cached(word: str, vocab) -> str:
    return _correct(word, vocab)


def _correct(word: str, vocab) -> str:
    """Fix a typo only when exactly one close catalogue word exists. 'iphone' never becomes 'phone' (first letter differs)."""
    if vocab is None or word in vocab or len(word) < 4 or not word.isalpha():
        return word
    limit = 1 if len(word) < 8 else 2
    best, best_d, tie = None, limit + 1, False
    for v in vocab:
        if v[0] != word[0] or not v.isalpha():
            continue
        d = _osa(word, v, limit)
        if len(word) == 4 and len(v) == 4 and sorted(v) != sorted(word):
            continue                        # "sofa" must never become "soft": short words may only gain/lose a letter or swap two
        if d < best_d:
            best, best_d, tie = v, d, False
        elif d == best_d and d <= limit:
            tie = True
    return best if best is not None and not tie else word


def tokenize(text: str, vocab=None) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", re.sub(r"(?<=\w)['’](?:s|m|re|ve|ll|d)\b|(?<=\w)n['’]t\b", "", text.lower())):
        if w in STOP:
            continue
        for t in SYNONYMS.get(w, [w]):
            t = _stem(t)
            if t in STOP:                       # "colours" -> "color" must be dropped like "colour" is
                continue
            if vocab is None:
                out.append(t)
                continue
            c = correct(t, vocab)
            if c == t and t not in vocab and w not in vocab and t == _stem(w):                  # "wireles" is a typo of "wireless", not the plural of "wirele"
                c2 = correct(w, vocab)
                c = c2 if c2 != w else c
            out.append(c)
    return out


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs = [Counter(d) for d in docs]
        self.len = [len(d) or 1 for d in docs]
        self.n = len(docs)
        self.avg = (sum(self.len) / self.n) if self.n else 1
        self.k1, self.b = k1, b
        self.post: dict[str, list[int]] = {}
        for i, c in enumerate(self.docs):
            for t in c:
                self.post.setdefault(t, []).append(i)
        self.vocab = frozenset(self.post)

    def search(self, query: list[str], limit: int = 30):
        q = set(query)
        if not q:
            return []
        scores: dict[int, float] = {}
        matched: dict[int, int] = {}
        for t in q:
            plist = self.post.get(t)
            if not plist:
                continue
            idf = math.log(1 + (self.n - len(plist) + 0.5) / (len(plist) + 0.5))
            for i in plist:
                f = self.docs[i][t]
                norm = f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg)
                scores[i] = scores.get(i, 0.0) + idf * f * (self.k1 + 1) / norm
                matched[i] = matched.get(i, 0) + 1
        hits = [(i, s, matched[i] / len(q)) for i, s in scores.items()]
        hits.sort(key=lambda h: (-h[1], h[0]))
        return hits[:limit]
