# Assistant upgrade — what changed, what was measured, what is still weak

## Method
1. Probed the original assistant with ~120 realistic questions (typos, Hinglish, needs, follow-ups) — it scored 100 % on its own
   53-question set but **43 %** on realistic ones (`questions_realistic.json`).
2. Fixed root causes, not phrasings; every fix has a named regression test in `tests/test_assistant_v2.py`.
3. Wrote two further sets (`questions_blind`, `questions_unseen`) and recorded the **first run before fixing anything**:
   original 45 % / 46 % → new 79 % / 74 %. After fixing what they exposed they read 100 %, which is no longer independent evidence.

## Bugs found in the original (all fixed, all tested)
- "noise cancelling headphones" was routed to the *cancellation policy*.
- "wireless headphones" returned the *wired* model ("Wireless: No" and "No noise cancelling." were indexed as positive evidence).
- After "VRT-1001", "and how long is the battery" was answered about a **different product**.
- Delivery questions were answered from the Returns section; "can I cancel my order" was refused as an order lookup.
- Filler words ("something", "mujhe", "every", "should") were treated as product terms, producing dead ends.
- Typo repair turned "sofa" → "soft", "cart" → "care", "sneakers" → "speaker" (the last one introduced and caught during this work).
- "at least 25 hours battery" was parsed as a minimum *price* (caught by the existing SmartMatch test).
- O(n²) list membership on `Product` dataclasses: 50–90 ms → 5–13 ms per request at 5 000 products.
- Found only by the real-browser test: "do you sell iPhones?" right after discussing a shoe was answered about the shoe.

## Label corrections (made after seeing system output — disclosed)
`nike shoes under 5000` → clarify (known type, unknown brand: offer the alternatives); B039 `running shoes in size 11` → clarify;
B058 `what about under 1500` → refuse (cheapest running shoe is ₹1,899); U036 kettle warranty → refuse; U047 `adidas football shoes` → refuse;
U001 expected id VRT-4002 → VRT-4001 (the steel *Water Bottle* is the better answer).

## Known limits
- Unknown words that are neither catalogue words nor in the stop-list make a query a "close match?" clarification rather than an answer.
  This is deliberate (never present a partial match as the answer) but costs fluency; extend `GENERAL_STOP` / `CONCEPTS` in `nlu.py`.
- Concepts and Hinglish are hand-written for this catalogue's vocabulary; a different catalogue needs its own concept entries.
- "Who pays for return shipping" is caught by a rule; other policy questions the text is silent on are caught only via unknown words.
- The Groq rewriter is unchanged and was not exercised against a live key.
- Deployment items from the original audit (e.g. `ALLOW_DEV_DATA` in `render.yaml`, per-process rate limiting) were not part of this pass.
