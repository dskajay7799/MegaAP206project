# Verity — The Conversational Shopping Assistant That Doesn't Lie

Verity is a full-stack, AI-powered shopping platform built for **R3 of the hackathon challenge**.
Every factual claim the assistant makes is cited to a product ID or policy section.
When the catalogue doesn't support an answer, Verity says so rather than inventing one.

## What it does

| Feature | Detail |
|---|---|
| **Grounded assistant** | BM25 retrieval → deterministic answer/clarify/refuse decision → optional Groq AI rewriting (verified before display). Understands needs ("something to carry my laptop"), typos, Hinglish, price ranges, superlatives ("longest battery"), questions about one product (features, sizes, colours, laptop fit), policy questions with real arithmetic (return window, shipping fee), and follow-ups ("the first one", "is it in stock", "add it to cart") — see *How the assistant understands you* |
| **Evidence explorer** | Every answer shows which records, fields and exclusions were used |
| **SmartMatch** | Explainable weighted score from catalogue facts; missing specs flagged, never assumed |
| **Value Lens** | Per-factor breakdown (budget, specs vs peers, price history, stock) |
| **Budget Basket** | Multi-slot basket within a budget; shows what fits and what doesn't |
| **Compare Studio** | Aligned specs, price bars, optional radar chart, user-weighted recommendation |
| **52-product demo store** | 8 categories, 3 SVG views per product, price history |
| **Full account system** | Registration, login, wishlist, preferences, saved comparisons and chats |
| **Admin dashboard** | Product/order/customer/category management, analytics charts |
| **Demo checkout** | Clearly disabled — no payment, card or UPI details ever collected |

## Quick start (local)

```bash
git clone <repo> && cd verity
pip install -r requirements.txt          # Flask, SQLAlchemy, Alembic, Playwright…
python scripts/build_demo_store.py       # generate 52 products + 156 SVG images
ALLOW_DEV_DATA=1 python -m backend.manage seed-demo --password-env DEMO_PASSWORD
ALLOW_DEV_DATA=1 python -m backend.manage create-admin --email admin@example.com
ALLOW_DEV_DATA=1 flask --app backend.app.main run --port 5000
# open http://localhost:5000
```

`.env` (copy from `.env.example`):
```
ALLOW_DEV_DATA=1
SECRET_KEY=change-me-32-chars-random
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=Your-Strong-Pass-1
DEMO_PASSWORD=Demo-Pass-2026x
SEED_DEMO=1
LOG_LEVEL=INFO
```

## Test suite

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ --ignore=tests/test_mobile.py -q
# 197 passed, 4 xfailed   (includes the real-browser tests; ~4 min)

# Evaluate the assistant on any question set (see "Evaluation" below):
ALLOW_DEV_DATA=1 DATA_DIR=/nonexistent \
  python -m backend.evaluate demo_store/questions_unseen.json --no-llm
```

## How the assistant understands you

Understanding only ever widens *what the shopper meant*; every sentence of the answer is still composed from catalogue / policy
records and carries an `[ID]` citation. Code: `backend/app/nlu.py` (language, no catalogue) and `backend/app/assistant.py` (decisions).

| Shopper says | What happens |
|---|---|
| "something to listen to music while jogging" | **Concepts** map needs to catalogue words (music → headphone/earbud/speaker, jogging → running/gym). The reading is shown in the reply and the evidence panel. Wording the catalogue doesn't use ("waterproof" vs "water-resistant") is never presented as an exact match. |
| "noice cancelling headfones", "retrun policy" | **Typo repair** — only when exactly one close known word exists (4-letter words may only gain/lose/swap a letter, so "sofa" never becomes "soft"). |
| "shoes for men" | The catalogue has no gender field, so Verity says it can't filter by it instead of silently ignoring the word. Recipients ("for my dad") are noted, not filtered. |
| "between 500 and 1000", "above 4000", "under 2k" | Price ranges. Numbers followed by a unit ("at least 25 hours") are never prices. |
| "which headphones have the longest battery", "most expensive product" | **Ranking** over typed specs; products with no value are reported, not guessed. |
| "does the kettle have auto shut-off?", "do the jeans come in 32?", "does it fit a 14 inch laptop?" | Answered from that one product's record — or refused with what *is* listed. |
| "can I return a shirt after 10 days?", "shipping on a 800 rupee order?" | Policy answers with exact arithmetic from the policy text; a policy that doesn't mention a product class (warranty on a kettle) is refused, not stretched. |
| "the first one", "compare the first two", "is it in stock", "add it to cart" | Conversation state is rebuilt from the earlier user messages (nothing stored server-side): last results, and the one product under discussion. |
| "hello", "what can you do", "tell me a joke" | Greeting / help / polite out-of-scope reply, instead of "not in our catalogue". |

## Evaluation

Behaviour accuracy = did it answer / ask / refuse as expected. Run each set with `python -m backend.evaluate <file> --no-llm`.

| Set | Questions | Original assistant | This version |
|---|---|---|---|
| `questions.json` (the project's own set) | 53 | 100 % | 100 % |
| `questions_realistic.json` (dev set, used while building) | 126 | 43 % | 100 % |
| `questions_blind.json` (first run, before any fix) | 67 | 45 % | **79 %** → 100 % after fixes |
| `questions_unseen.json` (first run, before any fix) | 54 | 46 % | **74 %** → 100 % after fixes |

**Read the first-run numbers, not the 100 %s.** Once a set has been used to find bugs it stops being independent; the honest estimate of
how the assistant behaves on questions it has never seen is the *first-run* figure (roughly 75–80 %). The remaining gap is mostly
unknown filler words the stop-list doesn't cover yet and needs-phrasings with no concept mapping. A few labels were corrected after
review (listed in the commit notes); all question files are plain JSON — add your own and re-run.
Accuracy alone also hid wrong *content* in answers whose status was right, so `citation_recall` (does the answer cite the expected
record?) and `responses_with_unsupported_claims` (must be 0) are checked too, and enforced by `tests/test_assistant_v2.py`.

## Deployment (Render + Netlify)

### Render (backend)
| Var | Value |
|---|---|
| `SECRET_KEY` | 32+ random chars |
| `DATABASE_URL` | Neon/Postgres URL |
| `APP_ENV` | `production` |
| `ALLOW_DEV_DATA` | `1` |
| `ADMIN_EMAIL` | first admin's email |
| `ADMIN_PASSWORD` | strong password |
| `SEED_DEMO` | `1` |
| `DEMO_PASSWORD` | demo accounts password |
| `CORS_ORIGINS` | `https://your-site.netlify.app` |
| `GROQ_API_KEY` | optional |

Start command: `gunicorn backend.app.main:app`

### Netlify (frontend)
`frontend/` is the publish directory. Set `_redirects`:
```
/api/*  https://your-backend.onrender.com/api/:splat  200
```
No `VERITY_API_BASE` needed when using the Netlify proxy.

## Architecture

```
backend/
  app/
    main.py          # Flask factory
    models.py        # SQLAlchemy ORM (22 tables)
    database.py      # Alembic migrations, SQLite dev / Postgres prod
    assistant.py     # Grounded assistant: routing, search, ranking, product questions, policy, conversation state
    nlu.py           # Language helpers: concepts, price ranges, ranking cues, references, small talk
    retrieval.py     # BM25 index, tokenizer, typo repair
    llm.py           # Optional Groq rewriter with claim verifier
    store.py         # DB-backed catalogue, Runtime index
    security.py      # Sessions, CSRF, scrypt passwords, rate limiting
    services/
      cart.py        # Server-side pricing, stock validation
      orders.py      # Demo checkout, atomic stock decrement, idempotency
      smartmatch.py  # Explainable weighted scoring
      valuelens.py   # Per-factor value breakdown
      basket.py      # Budget basket builder
      compare.py     # Comparison studio
      analytics.py   # Admin charts from stored rows
      recommend.py   # Preference-driven recommendations
    routes/          # catalog, assistant, auth, account, shop, admin
frontend/
  index.html
  js/
    app.js / router.js / store.js / api.js / dom.js / ui.js / charts.js
    assistant.js     # Chat panel with evidence explorer
    views/           # home, shop, product, cart, wishlist, compare,
                     # smartmatch, basket, auth, account, admin, info
  styles/            # base.css, components.css, views.css
  assets/
    fonts/           # Self-hosted Bricolage Grotesque + Instrument Sans
    products/        # 156 SVG illustrations (3 per product)
demo_store/
  catalogue.json     # 52 synthetic products
  policy.txt         # Returns, shipping, warranty, cancellation
  questions.json            # the project's own 53 evaluation questions
  questions_realistic.json  # 126 natural-phrasing questions (dev set)
  questions_blind.json      # 67 questions, first run was before any fix
  questions_unseen.json     # 54 questions, first run was before any fix
```

## Demo walkthrough (hackathon judges)

1. **Home** → hero with 3D product stage, SmartMatch composer, featured grid
2. **Ask Verity** → "wireless headphones for studying, commuting, long battery, under ₹3,000" → ranked matches with score breakdown; open "Evidence" to see cited fields
3. **Shop** → filter by Electronics, sort price low→high, add Halo ANC to cart
4. **Product page** → gallery zoom, colour picker, "Ask Verity about this product"
5. **Compare** `/compare?ids=VRT-1001,VRT-1002` → radar chart, weighted sliders
6. **SmartMatch** `/smartmatch` → type a need, adjust priority sliders live
7. **Budget Basket** `/basket` → "study setup · ₹5,000" → three basket configurations
8. **Cart** → checkout button shows "disabled in this demo" — no payment collected
9. **Register** → preferences → wishlist → recommendations
10. **Admin** `/admin` → charts from seeded orders, edit a product (price change reflects in assistant immediately)

## Security limitations (demo build)

- Checkout is disabled (`CHECKOUT_ENABLED=0`). No order can be created.
- No real email delivery (reset link shown in response when `DEV_SHOW_RESET_LINK=1`).
- Rate limiting is per-process (not shared across Gunicorn workers in production — use Redis for that).
- No real payment provider is integrated anywhere.
