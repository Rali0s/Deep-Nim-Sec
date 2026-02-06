Here’s a clean, copy-paste “builder prompt” you can drop into Replit to scaffold the app exactly how you want it.

---

# Build a Head-to-Head “Duel Mode” game with Stripe (no fully-anonymous users)

**Goal:** A full-stack TypeScript app that lets two players duel in real time. Users may browse anonymously, but must minimally identify (email-only auth) to start/join a duel or purchase via Stripe. Integrate Stripe Checkout + Customer Portal. Ship with test data and end-to-end webhook handling.

## Tech stack (use these unless you have a strong reason not to)

* **Front end:** Next.js 14 (App Router), TailwindCSS, shadcn/ui
* **Realtime:** Socket.IO
* **Backend:** Next.js API routes
* **Database:** Prisma + SQLite (file-based; works on Replit)
* **Auth:** Passwordless email “magic code” (DIY minimal auth, no 3rd-party provider)
* **Payments:** Stripe Checkout + Billing Portal (test mode)
* **State mgmt:** React Query (TanStack)
* **Validation:** Zod

## Environment variables

Create a `.env` with:

```
DATABASE_URL="file:./dev.db"
STRIPE_SECRET_KEY="sk_test_..."
STRIPE_PUBLISHABLE_KEY="pk_test_..."
STRIPE_WEBHOOK_SECRET="whsec_..."
APP_URL="http://localhost:3000"
```

## Data model (Prisma)

* `User { id, email (unique), createdAt, updatedAt, stripeCustomerId? }`
* `Match { id, status (WAITING|ACTIVE|COMPLETE|CANCELLED), mode (DUEL), createdAt, updatedAt }`
* `MatchPlayer { id, matchId, userId, score (int), isHost (bool), joinedAt, leftAt? }`
* `Round { id, matchId, number (int), prompt (string), hostAnswer?, guestAnswer?, winnerUserId?, startedAt, endedAt? }`
* `Purchase { id, userId, product (TIER_PLUS|HINT_PACK|SLOWMO|SECOND_CHANCE|BOSS_PASS|COMP_CORE_PACK), quantity, unitAmount, currency, stripeSessionId, status (PAID|REFUNDED), createdAt }`
* `Inventory { id, userId, hints (int), slowmo (int), secondChance (int) }`

Run `prisma migrate dev` + seed script.

## Pricing (seed these Stripe Products/Prices in code as “known IDs” you can override via env if present)

* TIER+ MONTHLY — **$3.99/mo** — removes ads, unlocks Expert difficulty, weekly tournaments, analytics
* HINT PACK (10x) — **$1.99** one-time
* SLOWMO — **$0.99** one-time (+6s per card/round)
* SECOND CHANCE — **$0.99** one-time (halve first miss penalty)
* BOSS PASS — **$1.49** one-time (weekly boss entry)
* COMP CORE PACK — **$3.99** one-time (3 hints, 1 slowmo, 1 second chance)

### Stripe flows to implement

1. **Checkout Session API**: POST `/api/stripe/checkout`
   Body: `{ priceId, quantity=1 }`
   Requires authenticated user (email-verified). Creates (or reuses) `stripeCustomerId`. Return `url` for redirect.
2. **Customer Portal API**: GET `/api/stripe/portal`
   Requires auth; creates a Stripe Portal session for that customer and returns `url`.
3. **Webhook**: POST `/api/stripe/webhook`
   Handle `checkout.session.completed` → record `Purchase` and increment `Inventory` and/or mark `TIER+` entitlement. Idempotent by `stripeSessionId`.

## Auth (no full anonymous for gated actions)

* Public pages viewable by anyone.
* To **Create/Join Duel**, **Buy**, or **Open Portal**, user must register with **email only**:
  Flow: user enters email → server sends 6-digit code → verify → set `auth` cookie (JWT) with `userId`. Add simple `/api/auth/send-code` and `/api/auth/verify`.
* Show username as the part before “@” (editable later).

## Duel Mode (realtime)

* **Lobby page**: “Create Duel” → creates `Match` with status `WAITING` and marks current user as host (`MatchPlayer.isHost=true`). Generate join URL `/duel/{matchId}` with a short invite code.
* **Matchmaking**: Optional “Quick Match” queue—place user into the oldest `WAITING` match (not their own) or create new if none available.
* **Start** when 2 players present. Server emits `match:started` via Socket.IO.
* **Rounds**: Best of 5 by default. Each round:

  * Server sends a round `prompt` (stub with a simple Q&A/mini-quiz or speed-click mini-task).
  * 20s timer (extendable to 26s if player uses **SLOWMO**).
  * Player may spend **Hint** to reveal a clue; reduce penalty with **Second Chance** if they miss first attempt.
  * On submit, server records answer, computes per-round winner, updates `score`.
* **Win Condition**: first to 3 wins or after 5 rounds highest score. Emit `match:completed`. Persist results.
* **Forfeits / Disconnects**: 30s grace; then other player wins round. If host leaves in `WAITING`, match cancels.

## Socket.IO channels

* `room:match:{matchId}`
  Events: `match:joined`, `match:left`, `match:started`, `round:started`, `round:state`, `round:ended`, `inventory:update`, `match:completed`, `system:error`
* Server validates JWT on connection; deny if not authed.

## Routes / Pages

* `/` – Landing, “Play Duel”, “How it Works”, “Pricing”.
* `/duel/new` – Create duel (auth required).
* `/duel/[id]` – Duel room UI with round panel, chat (basic), timers, power-ups (Hint/SLOWMO/SecondChance) and scoreboard.
* `/account` – Email, entitlements (TIER+), inventory, “Manage Billing” (Stripe Portal).
* `/shop` – List products → click “Buy” → call Checkout API. Show test card hint (4242…).
* `/auth` – Email login (send code + verify).
* `/admin` – Minimal admin: list matches/users/purchases (behind a simple server-side check of allowed emails).

## UI/UX details

* Use shadcn/ui (Cards, Button, Dialog, Badge, Tabs, Toast). Tailwind for layout.
* Clear **“You must sign in (email only) to duel or purchase.”** gate where relevant.
* Show “TIER+ active” badge when subscription is found for user.
* Display inventory counts (hints, slowmo, second chance).
* Simple toast feedback on socket events and purchases.

## Security & ops

* JWT in HttpOnly cookie, short-lived (24h) with server rotation secret.
* Zod validate all request bodies. Rate limit auth endpoints.
* Stripe webhook: verify signature using `STRIPE_WEBHOOK_SECRET`.
* Idempotent purchase handling; guard against duplicate increments.
* Server-side guard: only a match’s two players can join its socket room.
* Add seed script to create a couple of fake users, a demo match, and inventory.

## Developer scripts

* `npm run dev` – start Next + Socket.IO
* `npm run db:push` – Prisma
* `npm run db:seed` – Seed data
* `npm run tunnel` – print local tunnel URL and help set it in Stripe webhook (display command and curl example)

## Acceptance criteria

* I can enter email, receive a mock 6-digit code in server logs (dev) and sign in.
* I can create a duel, copy an invite link, and join from a second browser; duel runs with timers and scoring.
* I can buy a HINT PACK via Stripe Checkout (test mode), webhook credits my Inventory, and the UI updates live.
* I can open the Stripe Customer Portal from `/account` to manage/cancel TIER+.
* I cannot create/join duels or purchase without signing in (browsing remains open).

## Nice-to-have (if quick)

* Minimal chat in duel room.
* “Rematch” button that reuses both players.
* Basic anti-cheat (server authoritative timers & results).

Please generate:

1. The Next.js app with file structure and all pages/routes above.
2. Prisma schema + migrations + seed.
3. Stripe server utilities and Checkout/Portal/Webhook API routes.
4. Socket.IO server and client hooks.
5. A polished duel UI (Tailwind + shadcn) with timers, scoreboard, and power-ups.
6. A concise README with setup steps, Stripe test instructions, and webhook configuration.


---

That’s it—run with this as your build brief.
