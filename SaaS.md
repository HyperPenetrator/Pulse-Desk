# Swasthya Grid — SaaS, Scale & Offline-Resilience Guide

### How to read this file

This is a third, additive layer on top of `Swasthya-Grid-Architecture-Guide.md` and `prompt.md`. It doesn't change the data model, roles, or module boundaries already defined — it answers a different question: **how does this run as a multi-tenant SaaS product under district-scale traffic, on bad connections, with an offline mode that doesn't quietly lose data or quietly do the wrong thing.**

One thing up front, because it matters for a system that dispatches ambulances: **"offline" cannot mean the same thing for every feature.** Logging today's footfall offline and syncing it later is safe. Deciding which facility an ambulance should go to, offline, on data that might be stale, is not the same kind of problem — and this guide treats it that way rather than papering over it. Section 5.1 draws that line explicitly.

---

## 1. What "SaaS" means here — the tenancy model

The paying customer in this domain is realistically a **State Health Department**, procuring the platform for some or all of its districts. That sets the tenancy boundary:

```
Tenant (State) → District → Facility (PHC/CHC) → Staff
```

This adds one level above what the original data model had: a `tenant_id` (state code) sitting above `district_code`. Every table that currently keys on `district_code` gets `tenant_id` added — `facilities`, `census_reference`, `nfhs_reference`, `datagovin_reference`, and the BigQuery reference tables.

### Pooled vs. dedicated — decide this per tenant, not once for the whole product

| Model | What it is | When to use it |
|---|---|---|
| **Pooled (shared)** | One set of infrastructure, all tenants share Cloud SQL/Cloud Run/Firestore, isolated by row-level `tenant_id` | Default. Cheaper, faster to onboard new states, fine for most deployments |
| **Dedicated (silo)** | A tenant gets its own Cloud SQL instance and project, same codebase | Large states with their own data-residency mandates, or any state whose contract requires it |

Build the **pooled model as the default**, but build it as Infrastructure-as-Code (Terraform modules) from day one, so spinning up a dedicated deployment for one demanding tenant is "run the same module with a new project ID," not a special one-off rebuild. Retrofitting isolation later, once data is already commingled, is the expensive path — decide the module structure now even if every tenant starts pooled.

### Tenant isolation enforcement

Don't rely on application-code filtering alone (`WHERE tenant_id = ?` on every query is one missed `WHERE` clause away from a cross-tenant data leak). Enforce it at the database layer with **Postgres Row-Level Security (RLS)** policies keyed on `tenant_id`, set from the authenticated session. The application can still forget a filter; the database can't.

---

## 2. Where "high volume" actually comes from

Don't scale uniformly — scale for the actual shape of the load, which is not one thing:

| Source | Pattern | Why it matters |
|---|---|---|
| **Facility staff logging** (footfall, inventory, attendance) | Steady, predictable, spread across the day per facility | Aggregates to a real number once you multiply by every facility in a district, but each individual write is small and not urgent-fast |
| **District/state dashboards reading FSI, alerts, heatmaps** | Read-heavy, often polling or subscribing continuously while a screen is open | Same aggregate data gets re-read by every admin watching a screen — this is where naive re-computation gets expensive fast |
| **Public landing page** | Spiky, can burst hard during a local outbreak, disaster, or just because it's the de facto "get help" page for a whole district | The one that can actually take the system down if not isolated from the rest |
| **Voice/SMS/call intake** | Bursty in the same way as the landing page, plus rate-limited by the telephony gateway itself | Already partially decoupled by Twilio's own queuing, but the webhook path into your backend still needs the same protection |

The architecture below treats these as **four different load shapes needing four different mitigations**, not one autoscaling group doing everything.

### 2.1 Decouple ingestion with a queue

Every write-ish endpoint that doesn't need to return a result synchronously (`voice/transcribe` intent-routing, `intake` triage scoring, footfall/inventory logs) should hit a **Pub/Sub topic**, not the database directly. The API's job becomes: validate input fast, ack the request, publish to the queue, return. A separate pool of Cloud Run **worker** instances drains the queue at whatever rate the database can actually sustain.

This is the single highest-leverage change for surviving a burst: the burst hits the queue (which absorbs spikes cheaply) instead of hitting Postgres connections directly (which doesn't).

**Exception:** the dispatch decision itself (§5) is latency-sensitive and partially synchronous by nature — it can't just sit in a queue for a minute. Keep that path separate and prioritized; see §2.5.

### 2.2 Cache the expensive reads

FSI per facility, district heatmaps, and alert counts get re-read constantly by dashboards but only need to change when underlying data changes. Put **Memorystore (Redis)** in front of these:

- District dashboard requests for FSI/heatmap data hit Redis first; only a cache miss or an explicit invalidation (new footfall log, new alert) triggers recomputation.
- Cache TTLs differ by criticality: FSI/heatmap data can be a minute or two stale without consequence (60–120s TTL); **facility bed/ambulance capacity data used by the dispatch engine gets a much shorter TTL (60–90s)** specifically because staleness there has real consequences — see §5.1.

### 2.3 Scale the database properly

- **Connection pooling** in front of Cloud SQL (Cloud SQL's built-in pooler, or PgBouncer) — serverless Cloud Run instances scaling up under load will otherwise open far more Postgres connections than Postgres wants.
- **Read replicas** for the dashboard read path (FSI queries, alert lists, heatmaps), keeping the primary free for the write path (intake, dispatch, logs). Dashboards reading from a replica that's a few seconds behind is fine; writes to the primary are not delayed by it.
- Apply the RLS policies from §1 on both primary and replicas.

### 2.4 Push the public landing page to the edge

The landing page is the most exposed surface to traffic you don't control the shape of. Serve it as a **statically generated / ISR page (Next.js)** behind **Cloud CDN**, not a per-request server render. A burst of traffic hitting a CDN-cached static page costs you almost nothing; the same burst hitting a server-rendered page for every visitor is how an unrelated news event takes your ambulance-dispatch system down with it.

The **form submission itself** (POST `/api/v1/intake`) still hits the real backend — that's fine, because the read-heavy part (loading the page) is what scales unpredictably, and that's exactly what's now offloaded to the CDN.

### 2.5 Load-shedding policy — decide this before you need it

Under genuine overload, decide in advance what degrades first. Suggested priority order, highest-protected first:

1. **Emergency intake → dispatch path** (landing page submission, voice/SMS/call triage) — never shed this
2. **Receptionist alert acknowledgment** — keep this fast; a facility not seeing an incoming patient is a real-world failure
3. **Staff logging** (footfall, inventory, attendance) — can tolerate a short queueing delay; this is exactly what §2.1's queue is for
4. **Dashboard analytics refresh** (FSI heatmaps, redistribution views) — first thing to degrade; serve slightly staler cached data, extend TTLs, or rate-limit refresh under load

Implement this as actual rate-limiting/priority rules (e.g., separate Pub/Sub topics with separate worker pools sized differently, so starving topic 4's workers can't starve topic 1's), not just a hope that autoscaling handles it.

---

## 3. Poor-bandwidth resilience

Design for **2G/EDGE (~50–100 kbps) as the worst realistic case**, not as an edge case you'll get to later. Most of rural India's mobile data experience sits between weak 3G and 4G with frequent drops — that's the actual target, not a fast office Wi-Fi connection.

### 3.1 Channel strategy — pick the right transport for the situation

| Channel | Survives poor signal because... | Use it for |
|---|---|---|
| **Plain voice call** | Voice calls work at signal strength where data fails outright; this is the most bandwidth-resilient channel that exists on a basic phone | Emergency intake when nothing else works — already in the architecture via the Dialogflow CX + Twilio voice path |
| **SMS** | Store-and-forward by design at the telecom layer; works at weaker signal than data, and a dropped connection doesn't lose a sent SMS the way a dropped HTTP request can lose a payload | Structured staff updates (stock/footfall/attendance) and dispatch confirmations to patients without smartphones |
| **WhatsApp/data-based chat** | Needs data, but tolerates intermittent connectivity better than a live web session (messages queue and deliver) | Patients who do have a smartphone and some data, as a richer alternative to SMS |
| **Web (landing page / dashboards)** | Needs a live-enough data connection for the session | Primary path when bandwidth is adequate; needs everything in §3.2–3.3 to degrade gracefully when it isn't |

The point isn't "use the web app" with SMS/voice as an afterthought — for the patient-facing emergency path specifically, **voice and SMS are the resilient channels and the web form is the convenience option for people who have good enough data to use it.** Architect with that priority, not the reverse.

### 3.2 Structured SMS as a real channel, not a stub

Give the SMS path an actual command grammar rather than free text everywhere, so it's parseable without needing an LLM round-trip on a channel that's already constrained:

```
STOCK PARACETAMOL 0          → stock update
FOOTFALL 42                  → today's footfall count
HELP <symptom text>          → triage/dispatch request (free text — this one needs the real triage pipeline)
```

On a parse failure, reply with a one-line format reminder rather than silently dropping the message. This keeps routine staff updates cheap and instant even on a 2G connection, while still routing genuine emergencies (`HELP ...`) into the full triage pipeline.

### 3.3 Payload and transport budget

Set actual numbers, not vague intentions:

- **Audio uploads:** encode at a low-bitrate codec (Opus, ~16 kbps mono) before upload — speech-to-text doesn't need broadcast-quality audio, and this alone cuts upload size by roughly an order of magnitude versus an unprocessed phone recording.
- **Resumable/chunked uploads:** a dropped connection mid-upload on 2G is normal, not exceptional. Use a chunked/resumable upload approach (e.g., the `tus` protocol, or hand-rolled chunk+retry) for voice uploads so a drop means "resume," not "start over."
- **API responses:** gzip/brotli everywhere, paginate list endpoints (20–50 records per page, not "return everything"), and support field selection so a dashboard widget that needs three fields doesn't pull the whole facility record.
- **Frontend JS budget:** target an initial load under roughly 200 KB gzipped for the public landing page specifically, since that's the surface most likely to be hit on a patient's basic data plan. Dashboards used by staff can be somewhat heavier, but still treat bundle size as a tracked metric, not an afterthought.

### 3.4 Prefer "installable web app" over "downloadable native app"

A native app's install size is itself a bandwidth cost paid once, up front, on the worst connection a user has — exactly backwards for this audience. Build the staff dashboards as an **installable PWA** (Add to Home Screen) instead of a native APK: same offline capability via service worker (§4), a fraction of the download size, and no app-store update friction for a government rollout across many districts.

---

## 4. Offline-first architecture for staff dashboards

This section is about the parts of the system where "capture now, sync later" is genuinely safe: footfall logging, inventory updates, attendance, and alert acknowledgment. §5 covers the part where it isn't.

### 4.1 Local-first writes

Every write action in the Receptionist and PHC In-charge dashboards writes to a local **IndexedDB** store first (a library like Dexie.js makes this manageable), updates the UI optimistically, and only then attempts to sync to the backend. The user never has to wait for a network round-trip to see their own action reflected, and the action isn't lost if the network is down at that exact moment.

Each locally-queued write carries:
- A client-generated UUID (so retries are idempotent — the server can recognize "I've already applied this one")
- A timestamp and the device/session that created it
- A monotonically increasing local sequence number, so order is preserved even if sync happens out of order

### 4.2 Sync queue, not a hope

Don't rely solely on the browser's Background Sync API — it's not universally supported and shouldn't be the only mechanism for something this important. Implement an explicit sync queue:

- A visible counter in the UI: "3 updates pending sync" — staff should never wonder whether their data went anywhere.
- Retry on reconnect with exponential backoff (start ~5s, cap ~5min), persisted in IndexedDB so the queue survives an app restart or even a phone reboot, not just an in-memory variable.
- A manual "retry now" button for when a staff member knows connectivity just came back and doesn't want to wait for backoff.
- A failure threshold (e.g., after N failed attempts over M hours) that flags an item for manual review rather than retrying forever silently.

### 4.3 Conflict resolution — pick the strategy per data type, not one rule for everything

| Data type | Strategy | Why |
|---|---|---|
| Footfall counts | Event-sourced delta ("+1 patient") rather than overwriting a running total | Two offline devices both logging patients today don't conflict if they're each contributing a delta, not racing to set the same absolute number |
| Inventory stock | Event-sourced delta (stock used/received) | Same reasoning — deltas commute, absolute overwrites from two stale clients don't |
| Attendance check-in | Idempotency key = `(staff_id, date)` | A duplicate sync of the same check-in is a no-op server-side, not a duplicate row |
| Alert acknowledgment | Server-authoritative state machine; client proposes a transition, server accepts or rejects based on current state | Prevents an offline device replaying a stale "acknowledge" after someone else already resolved the alert from a different device |

The common thread: wherever possible, queue **events/deltas**, not **snapshots**. Snapshots are what create conflicts when two offline writers disagree about the current value; deltas mostly just add up correctly regardless of order.

### 4.4 Service worker caching — and showing staleness honestly

- **App shell** (JS/CSS/static assets): cache-first via the service worker — the app itself should open instantly offline.
- **Reference data** (facility list, staff roster, inventory item list): stale-while-revalidate — show the last-cached version immediately, refresh in the background, and **display a "last updated" timestamp in the UI** rather than presenting cached data as if it were live. A receptionist should be able to tell at a glance whether what they're looking at is current.

---

## 5. The honest part: dispatch decisions can't be fully offline, so design the degraded mode deliberately

### 5.1 Draw the line explicitly

| Can be fully offline-first | Cannot — needs a degraded-mode design instead |
|---|---|
| Footfall logging | **Matching a patient to a specific facility/ambulance** — this depends on *current* bed/ambulance availability, which by definition can't be known with confidence from stale cached data |
| Inventory updates | |
| Attendance logging | |
| Alert acknowledgment (an action on a known alert) | |
| Viewing recently-cached dashboard data | |

This isn't a limitation to hide — it's the correct engineering answer. Pretending a dispatch decision made on data that might be 20 minutes stale is "offline support" would be worse than admitting the constraint, because it fails exactly when it matters most: a real emergency in a connectivity dead zone.

### 5.2 Degraded-mode dispatch protocol

When the landing page or intake pipeline detects it can't reach live facility-capacity data (cache beyond its short TTL, or no connection at all):

1. **Don't silently dispatch on stale data.** Show the last-known nearest facility and its last-known capacity, with the staleness timestamp clearly visible, and require explicit confirmation rather than auto-confirming.
2. **Fail over to the voice channel automatically where possible.** If the web form can't reach the backend, the landing page's confirmation step should surface the emergency phone number prominently — the voice/SMS path (§3.1) doesn't depend on the same connectivity the web form just failed on, since it can run over plain cellular signal.
3. **Keep a non-software fallback at every facility.** A laminated card at the receptionist desk with the district escalation phone tree, updated whenever it changes. This sounds low-tech because it is — and it's exactly the kind of fallback that still works when every layer of the software stack is degraded at once. Critical rural infrastructure that has *only* a software fallback for its most life-critical feature is taking on more risk than it needs to.

### 5.3 Voice-to-text under offline conditions

Cloud Speech-to-Text needs connectivity — there isn't a free lunch here. The honest fallback:

- Record and locally store the compressed audio blob (§3.3's codec choice) immediately, queue it for upload like any other offline write (§4.1–4.2).
- Give the staff member the option to type a short manual note alongside the recording ("Paracetamol — out") so the *intent* of the update isn't blocked on transcription even before sync happens — the voice recording still syncs and gets transcribed properly once connectivity returns, but the manual note means nothing is silently waiting in limbo with no visible trace of what was reported.

---

## 6. Observability — this is emergency infrastructure, treat monitoring accordingly

A SaaS platform that dispatches ambulances needs operational visibility proportional to that responsibility, not generic "add some logging" advice:

- **Structured logging** across the API, workers, and webhook handlers, tagged with `tenant_id`/`district_code`/`facility_id` so an incident can be traced to exactly which tenant and facility it affected.
- **Error tracking** (e.g., Sentry) wired specifically to flag failures on the dispatch and intake paths at a higher severity than failures on, say, the analytics dashboard.
- **Uptime monitoring with paging**, specifically on `/api/v1/intake`, `/webhook/dialogflow`, and the Twilio webhook — these are the paths where downtime has a direct real-world consequence, and they should page an on-call human, not just log a metric nobody looks at until morning.
- **A public status page** per tenant/state, since district administrators and PHC in-charges are exactly the people who need to know "is the platform down right now, or is it just my connection" without filing a support ticket to find out.

---

## 7. What this adds to the stack

Everything below is additive to the tech stack table in the original architecture guide:

| Component | Purpose |
|---|---|
| Pub/Sub | Decouples ingestion writes from the database write path (§2.1) |
| Memorystore (Redis) | Caches FSI/heatmap/capacity reads (§2.2) |
| Cloud SQL connection pooling + read replicas | Database scaling for high concurrent load (§2.3) |
| Cloud CDN | Edge caching for the public landing page (§2.4) |
| Dexie.js (IndexedDB wrapper) | Local-first writes on staff dashboards (§4.1) |
| Workbox (service worker tooling) | App-shell caching and stale-while-revalidate data caching (§4.4) |
| `tus` (or equivalent resumable upload protocol) | Chunked/resumable voice uploads on poor connections (§3.3) |
| Terraform | Per-tenant infrastructure templates for the pooled/dedicated tenancy model (§1) |
| Sentry (or equivalent) + uptime/paging tool | Operational observability proportional to the platform's real-world stakes (§6) |

---

## 8. Where this fits in the rollout plan

This layer isn't a separate phase that comes "after" the original MVP→V3 plan — most of it needs to be in place *before* a real district relies on the platform, because retrofitting tenancy isolation and offline support onto live data is much harder than building them in from the start. Suggested sequencing against the original phases:

| Original phase | Add from this guide |
|---|---|
| MVP | RLS-based tenant isolation from day one (§1), even if there's only one tenant so far — this is much cheaper to do before multi-tenant data exists than after |
| MVP → V1 | Pub/Sub ingestion decoupling (§2.1), basic offline-first writes for the Receptionist dashboard (§4) |
| V1 → V2 | Redis caching (§2.2), read replicas (§2.3), CDN for the landing page (§2.4), structured SMS grammar (§3.2) |
| V2 → V3 | Degraded-mode dispatch protocol (§5.2) — this should land *before* the full multilingual pipeline goes live in production, not after, since it's the safety net under the highest-stakes feature |
| Ongoing | Observability (§6) from the first real deployment onward, not bolted on after the first incident |

If you'd like, I can fold matching build stages for this layer into `prompt.md` so they slot into the existing Antigravity stage sequence rather than living only as prose here.
