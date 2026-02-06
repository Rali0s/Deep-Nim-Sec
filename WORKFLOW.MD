# Agile Process Flow – LLM Data‑Structure Project

*Last updated: Oct 26, 2025*

## 0) Overview

**Goal:** Deliver a production‑ready LLM-powered app and data pipeline with measurable model quality, a clean UI, and a reliable lifecycle (CI/CD, observability, compliance).

**Work Strategy:** Scrum‑ish, 2‑week sprints, incremental releases behind feature flags. Dual tracks for **Discovery** (research, spikes, design) and **Delivery** (build, test, ship).

**Core Tools (suggested):** GitHub, Issues/Projects, PR checks; GCP (GCE/GKE, Cloud Run, Artifact Registry, Secret Manager, Cloud Build, Cloud Storage, BigQuery); MLOps (Weights & Biases or MLflow, Vertex AI optional); DX (pre‑commit, ruff/black, mypy); QA (pytest + Playwright); Obs (OpenTelemetry + Grafana/Cloud Monitoring).

---

## 1) EPICS mapped to your 8 items

### Epic A — Google Compute (Infra Foundation)

**Objective:** Provision secure, cost‑controlled GCP footprint for data, training, and serving.

* **Key Deliverables**

  * Project(s) + IAM baseline (least privilege), service accounts, folders
  * Networks: VPC, subnets, private service access; restricted egress
  * Artifact Registry, Cloud Storage buckets, BigQuery dataset(s)
  * CI/CD: Cloud Build or GitHub Actions → Cloud Run/GKE deploys
  * Observability stack (logs, metrics, traces), budget alerts
* **Entry Criteria:** Org access; billing account; domain; repo.
* **Exit Criteria (DoD):** One‑click infra deploy; policy checks pass; golden path E2E smoke test green.
* **Dependencies:** None

### Epic B — Custom Model

**Objective:** Baseline model + training loop with experiment tracking & evals.

* **Key Deliverables**

  * Training/finetune scripts; data loaders; tokenizer config
  * Experiment tracking (W&B/MLflow), metrics dashboard
  * Offline evaluation suite; golden prompts; bias/robustness checks
  * Model registry; versioning; artifact promotion gates
* **Exit Criteria:** Reproducible run; metrics ≥ baseline targets; model artifact registered.
* **Dependencies:** A, C

### Epic C — Data Sets

**Objective:** Curate, clean, and label datasets powering the model & retrieval.

* **Key Deliverables**

  * Ingestion pipelines (PDF/ePub → text), schema, data contracts
  * Quality gates: dedupe, PII scrub, chunking, metadata, lineage
  * Ground‑truth set for eval; split strategy; licensing audit
* **Exit Criteria:** Data quality report ≥ thresholds; signed off by QA.
* **Dependencies:** A

### Epic D — Initial Phase moving along

**Objective:** Deliver an end‑to‑end thin slice (ingest → train → serve → UI stub).

* **Key Deliverables:** "Hello world" vertical: small dataset, tiny model, minimal UI, single endpoint.
* **Exit Criteria:** Demoable flow; latency & cost within budget; logs/metrics visible.
* **Dependencies:** A, B, C

### Epic E — Bookmark Parser (URLs → Content)

**Objective:** Build a bookmark/URL parser to enrich datasets (crawl, parse, normalize).

* **Key Deliverables**

  * URL queue, robots compliance, rate limiting, retry/backoff
  * HTML → Markdown/clean‑text; boilerplate removal; canonicalization
  * Metadata capture (title, authorship, date), checksum, dedupe
  * Safety: domain allowlist/denylist, content filters, license tags
* **Exit Criteria:** Batch of URLs → clean corpus; quality report; failures triaged.
* **Dependencies:** A, C

### Epic F — RE‑Train Model

**Objective:** Incorporate new data (incl. bookmarks) and re‑train/prompt‑tune.

* **Key Deliverables:** Updated datasets → training jobs; eval deltas; regression guardrails.
* **Exit Criteria:** KPIs improve without regressions; promoted to staging.
* **Dependencies:** B, C, E

### Epic G — Build UI

**Objective:** Ship a polished, accessible web app for querying and managing the model/data.

* **Key Deliverables**

  * UX flows: ingestion status, search, chat, export
  * Auth (OIDC), roles/permissions, audit logging
  * Latency budgets; streaming responses; offline/empty states
  * E2E tests; accessibility checks
* **Exit Criteria:** NFRs pass (perf, a11y, security); UAT sign‑off; staging launch.
* **Dependencies:** D, F

### Epic H — App Lifecycle

**Objective:** Production hardening and operations.

* **Key Deliverables**

  * CI/CD with environments; feature flags; rollout/rollback
  * Monitoring SLOs; on‑call runbook; incident drills
  * Data retention, GDPR/CCPA controls; model/version deprecation policy
* **Exit Criteria:** Prod launch checklist green; week‑1 stability report.
* **Dependencies:** A, G

---

## 2) User Stories (samples)

* As a **data engineer**, I can configure an allowlist of domains so the bookmark parser only crawls approved sources, ensuring licensing compliance.
* As an **ML engineer**, I can compare experiments by dataset version and see eval deltas so I can pick the best model.
* As a **researcher**, I can tag a URL batch with topics and authors, enabling focused re‑training.
* As a **user**, I can chat with the model and export answers with citations so I can verify sources.

**INVEST:** Independent, Negotiable, Valuable, Estimable, Small, Testable.

---

## 3) Backlog (by Epic)

### A) Google Compute

* IaC repo (Terraform) & pre‑commit checks
* VPC, subnets, Private Google Access, NAT
* GCS buckets (raw, bronze, silver, gold); lifecycle rules
* Secret Manager; KMS; service accounts & IAM bindings
* Cloud Build pipelines; Artifact Registry; base containers
* Budget alerts; org policies; VPC‑SC (if needed)

### B) Custom Model

* Dataset loader abstractions; tokenizer config
* Finetune loop; mixed‑precision; gradient accumulation
* Eval harness (exact match, F1, BLEU/ROUGE, task‑specific)
* Safety filters (prompt/response); red‑team prompts
* Model registry & promotion gates

### C) Data Sets

* PDF/ePub → text (pypdf, pdfminer.six + heuristics)
* Structure recovery (headings, lists, tables); metadata
* PII detection/removal; license tagging
* Ground‑truth/labeling guidelines; adjudication

### D) Thin Slice

* Minimal ingestion job (GCS trigger)
* Tiny model (e.g., 1–3B or adapter) hosted on Cloud Run
* UI stub with streaming chat & basic citations

### E) Bookmark Parser

* Robots.txt obey; politeness; caching; retries
* HTML → Markdown; boilerplate removal (readability)
* Canonical URL; dedupe via checksum; sitemap support
* Domain policies & license store; error dashboard

### F) Re‑Train

* Data version bump; curated negatives; hard examples
* Scheduled training jobs; eval regression checks
* Canary model serving & A/B switch

### G) UI

* Auth (OIDC) + RBAC; audit trails
* Search + RAG view (chunks, sources, scores)
* Dataset/Job dashboards; export CSV/JSON
* a11y (axe), perf budgets, E2E tests (Playwright)

### H) Lifecycle

* CI/CD: build→scan→test→deploy→verify→notify
* SLOs: latency, availability, cost per request
* Tracing (OTel), logs sampling, alerts, runbooks
* Privacy (DPIA), retention windows, DSR endpoints

---

## 4) Architecture Checkpoints

* **Data plane:** Ingestion → normalization → storage tiers → indexing (e.g., vector DB if using RAG) → access layer.
* **Model plane:** Training/finetune → eval → registry → rollout.
* **Control plane:** CI/CD, IaC, secrets, authz, observability.

---

## 5) Sprint Plan (proposal; 2‑week sprints)

**Sprint 1 – Infra & Thin Slice**

* IaC baseline, buckets, CI/CD skeleton
* Minimal ingest of a sample PDF/ePub
* Serve baseline model; UI stub streams text
* **Demoable:** Ingest→query round‑trip with logs/metrics

**Sprint 2 – Data Quality & Parser**

* Structure recovery, PII scrub, quality report
* Bookmark parser MVP (allowlist + HTML→MD)
* Eval harness v1; experiment tracking live
* **Demoable:** URL batch → clean corpus; eval dashboard

**Sprint 3 – Retrain & UI**

* Re‑train with new corpus; regression gates
* UI search/RAG; auth; audit logging
* **Demoable:** Model v2 beats v1; secure UI flows

**Sprint 4 – Hardening & Launch Prep**

* SLOs, alerts, runbooks; feature flags
* Privacy/retention; canary + rollback
* **Demoable:** Incident drill; release checklist

---

## 6) Definition of Done (Global)

* Code reviewed; tests ≥ 80% critical paths; lint/static checks pass
* Reproducible pipeline; artifacts versioned; docs updated
* Security: secrets in Secret Manager; least‑privilege IAM
* Observability: logs/metrics/traces wired; dashboards exist
* Accessibility: key screens pass WCAG AA checks

---

## 7) Risks & Mitigations

* **Data licensing/PII leakage** → Domain allowlists, license tags, PII scrub, legal review
* **Cost overruns** → Budgets/quotas, autoscaling, spot/Preemptible where safe
* **Model regressions** → Eval gates, canary deploys, rollback script
* **Crawl block/robots issues** → Pre‑flight robots check, rate limit, backoff
* **Vendor lock‑in** → IaC, containerized workloads, abstraction layers

---

## 8) RACI (roles)

* **Product Owner (PO):** Backlog, priorities, accept stories
* **Tech Lead (TL):** Architecture, quality gates, reviews
* **ML Engineer (MLE):** Training, evals, model registry
* **Data Engineer (DE):** Ingestion, pipelines, quality
* **Frontend Engineer (FE):** UI/UX, accessibility
* **SRE:** Infra, CI/CD, SLOs, incidents
* **Security/Compliance:** Reviews, DPIA, audits

---

## 9) KPIs & Quality Targets

* **Model:** Task metric +Δ over baseline; harmful output rate ↓
* **Data:** % clean documents; parser success rate; coverage
* **App:** P50 < 600ms, P95 < 2.5s; error rate < 1%
* **Ops:** SLO 99.5%; MTTR < 30m; cost/request target $X

---

## 10) App Lifecycle (Pipeline Stages)

1. **Plan:** Issue → spec → design review
2. **Code:** Branch, PR, checks (lint/test/sec)
3. **Build:** Containerize; SBOM; vulnerability scan
4. **Test:** Unit → integration → E2E
5. **Deploy:** Staging → canary → prod
6. **Verify:** Smoke, SLOs, user analytics
7. **Operate:** Monitor, alert, on‑call
8. **Improve:** Post‑incident review; backlog updates

---

## 11) Next Actions (concrete)

1. Create Terraform skeleton + bootstrap GCP project & buckets
2. Stand up experiment tracker; push a dummy training run
3. Land parser MVP (allowlist + HTML→MD) and quality report
4. Wire eval harness with a small, trusted ground‑truth set
5. Ship Thin Slice demo behind a feature flag
