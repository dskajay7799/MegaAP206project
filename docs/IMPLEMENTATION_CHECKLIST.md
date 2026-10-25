# Verity upgrade — audit and implementation checklist

## Stage 1 audit (state of the repository before this upgrade)

**Architecture.** Flask API (`backend/app/main.py`), a deterministic grounded assistant (`assistant.py`, BM25 `retrieval.py`),
an optional Groq rewriter guarded by `llm.verify()`, optional Neon logging (`db.py`, raw psycopg2), vanilla-JS single page
(`frontend/`, hash routes, `sessionStorage` only), Render (API) + Netlify (static) config.
Catalogue and policy are read from JSON/text files **into memory at import time**; there is no user, cart, order or admin concept.

**Working features that must be preserved.** BM25 retrieval with synonyms/typo repair · answer / clarify / refuse decisions ·
every sentence cited with `[ID]` · verifier that binds numbers and stock wording to the cited record · multi-turn budget/attribute
constraints · compare up to 4 · browse filters + pagination · rate limiting · CORS allow-list · CSP · `evaluate.py`
(37 dev questions at 100 %) · 29 passing tests including an 8-viewport Playwright suite.

**Baseline.** `pytest tests` → 29 passed. `python -m backend.evaluate dev_data/questions.json --no-llm` → behaviour accuracy 1.0, 0 unsupported claims.

**Risks found.**
- Catalogue lives only in memory → admin edits, inventory and orders cannot be persisted without a database-backed catalogue.
- `DATABASE_URL` meant *optional analytics*; Render's free disk is ephemeral, so accounts/orders **must** use Postgres in production (SQLite is for local dev only).
- `UNSUPPORTED` regex makes the assistant refuse "account / payment / order" questions. The assistant still has **no evidence source** for those, so it keeps refusing but now points to the real account pages.
- CSP is `script-src 'self'; style-src 'self'` → no CDN chart/3D libraries, no inline styles; charts and 3D are hand-built SVG/CSS.
- Right-most `X-Forwarded-For` hop would collapse every user into one bucket behind a Netlify proxy → configurable proxy-hop count.
- Official R3 data (5 000 products, 150 questions) is **not in the repo**; the demo store is synthetic and labelled.

## Decisions

| Topic | Decision |
|---|---|
| Persistence | SQLAlchemy 2 + Alembic. Postgres (Neon) in production, SQLite locally. Money stored as integer paise. |
| Catalogue | DB is authoritative after first import; assistant index rebuilds when `catalogue_version` changes. Files remain seed sources. |
| Auth | Server-side sessions: random token in an HttpOnly cookie, SHA-256 of it in the DB, HMAC-bound CSRF token, scrypt password hashes, DB lockout + IP limiter. No tokens in `localStorage`. |
| Netlify ↔ Render | Netlify proxies `/api/*` to Render so cookies are first-party. Cross-origin mode (SameSite=None + CORS credentials) is supported but documented as second choice. |
| Images | The build sandbox has no access to stock-photo hosts, so photography could not be sourced. Verity ships a reproducible generator (`scripts/generate_product_images.py`) producing license-free product illustrations (3 views each), labelled as illustrations. Admin can replace any image with an https URL. |
| Charts / 3D | Hand-written SVG charts with data tables; CSS 3D (perspective, tilt, parallax). No external libraries. |
| Scores | SmartMatch is a deterministic weighted sum over catalogue facts, shown criterion by criterion. Missing data counts as *unverified*, never assumed. |
| Payments | Demo checkout only. No card data is collected; confirmation says no payment was taken. |

## Checklist

- [x] Stage 1 — audit, baseline tests, checklist
- [ ] Stage 2 — design system, storefront, product pages, 48-product catalogue with images
- [ ] Stage 3 — DB models + migrations, auth, accounts, cart, checkout/orders, admin
- [ ] Stage 4 — SmartMatch, Value Lens, Budget Basket, Comparison Studio, price history, evidence explorer, preferences
- [ ] Stage 5 — tests (API + browser, 8 viewports), security review, performance pass, README/deploy docs

Status notes are appended at the bottom of this file as stages complete.
