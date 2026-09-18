# Production-ready 3-tier Python app on GCP — project blueprint

**Role:** Senior DevOps Project Lead
**Audience:** Rajesh (4+ yrs AWS/GCP DevOps, no prior Azure) — beginner→advanced path
**Goal:** A demo that behaves like a real production system, not a toy

---

## 1. Real-world framing

Think of this as **"TechMart"** — a small e-commerce company launching an order-management app.

| Tier | Component | Real-world job |
|---|---|---|
| Presentation | Python (FastAPI/Flask) + Jinja/React static assets | Storefront the customer sees |
| Application | Python FastAPI backend, REST APIs | Order logic, pricing, inventory checks |
| Data | Cloud SQL (PostgreSQL) | Orders, customers, inventory — the source of truth |

A platform team (you) is asked to make this **shippable safely, repeatedly, and observably** — not just "deployed once." That's the actual deliverable: not the app, the *paved road* around it.

---

## 2. Corrections to your original requirements

Your list mixed a few things that need to be untangled before building — this is exactly the kind of scoping a lead has to do up front:

1. **"Deploying GKE by Cloud Build and Cloud Run"** — GKE and Cloud Run are two *separate, alternative* compute platforms, not a pair used together for one deployment. Cloud Build is a CI *builder*, not a deploy target.
   - **Correction:** Pick GKE as primary compute (you asked for Kubernetes explicitly). Optionally show Cloud Run as an *alternate deployment path* for a stateless piece (e.g. a lightweight internal tool) to demonstrate both — but the 3-tier app deploys to GKE.
2. **"Cloud Build ... GitHub Actions"** — you named two CI systems. Running both in parallel adds no value for a demo.
   - **Correction:** Standardize on **GitHub Actions** as the single CI/CD orchestrator (matches your Git/GitHub Actions requirement). Cloud Build is dropped, or mentioned only as an alternative note.
3. **"Service account and OIDC Authentication"** — a static Service Account *key* and OIDC are opposites in intent (OIDC exists to eliminate long-lived keys).
   - **Correction:** Use **Workload Identity Federation (WIF)** — GitHub Actions authenticates to GCP via OIDC, impersonating a scoped Service Account, with **zero downloaded keys**. This is the actual production pattern.
4. **"Security tools for code and images"** — under-specified; a real pipeline needs 4 distinct scan categories, not one.
   - **Correction:** SAST (code), SCA (dependencies), container image scanning, and IaC scanning are four separate gates — listed below.
5. **Missing from your list, required for "production-ready":** Terraform remote state + locking, secrets management, ingress/TLS, autoscaling, network policy, GitOps/CD separation, alerting, cost guardrails, and a rollback strategy. These are added below as explicit phases — a demo that skips them isn't representative of what you'd actually be asked to build in a real role.

---

## 3. Corrected architecture (see diagrams above)

**CI (build-time):** GitHub → GitHub Actions (OIDC → GCP, no keys) → lint/test → SAST/SCA/secrets scan → Docker build → Trivy image scan → push to Artifact Registry (fails the build on critical CVEs).

**IaC:** Terraform, GCS backend with state locking, modules for VPC, GKE (Autopilot), Artifact Registry, Cloud SQL, IAM, WIF pool, monitoring — plus `trivy config` (or Checkov) scanning the plan itself. (tfsec is unmaintained; Aqua merged its check library into Trivy.)

**CD (deploy-time):** GitHub Actions applies Kubernetes manifests/Helm chart to GKE (or, at advanced stage, ArgoCD pulls from a Git repo — GitOps).

**Runtime:** GKE Autopilot cluster, 3 tiers as separate Deployments + Services, Ingress + cert-manager for TLS, HPA, NetworkPolicies isolating tiers, Cloud SQL reached via private IP (no public DB exposure).

**Observability:** `kube-prometheus-stack` (Prometheus + Grafana + Alertmanager) via Helm, dashboards per tier, alerts to Slack/email.

---

## 4. Suggested repo layout

```
techmart-devops/
├── app/
│   ├── frontend/          (Dockerfile, source)
│   ├── backend/           (Dockerfile, source, requirements.txt)
│   └── db/                (migration scripts)
├── terraform/
│   ├── modules/ (vpc, gke, artifact-registry, cloudsql, iam-wif, monitoring)
│   └── envs/ (dev, staging, prod — separate state per env)
├── k8s/
│   ├── base/ (Kustomize/Helm base manifests)
│   └── overlays/ (dev, staging, prod)
├── .github/workflows/
│   ├── ci.yml       (lint, test, scan, build, push)
│   └── cd.yml       (deploy to GKE)
└── monitoring/ (Prometheus rules, Grafana dashboards as code)
```

---

## 5. Execution roadmap — beginner → advanced

### Phase 1 — Foundations (Beginner)
1. Create GCP project, enable billing, enable APIs (`container.googleapis.com`, `sqladmin.googleapis.com`, `artifactregistry.googleapis.com`, `iam.googleapis.com`, `cloudresourcemanager.googleapis.com`).
2. Create the GitHub repo, set up branch protection on `main`.
3. Write Dockerfiles for frontend and backend (multi-stage, non-root user, `.dockerignore`).
4. Manually build and run containers locally with `docker compose` to prove the 3 tiers talk to each other.

### Phase 2 — Infrastructure as Code (Beginner→Intermediate)
5. Initialize Terraform with a **GCS backend** (versioned bucket, state locking).
6. Write modules: VPC + subnets, GKE Autopilot cluster, Artifact Registry repo, Cloud SQL (private IP, automated backups), IAM.
7. `terraform plan` → review → `terraform apply`. Tag everything with labels (`env`, `owner`, `cost-center`).

### Phase 3 — Keyless CI/CD auth (Intermediate)
8. Create a **Workload Identity Federation pool + provider** trusting GitHub's OIDC issuer, scoped to your repo/branch.
9. Create a dedicated Service Account with least-privilege roles (`roles/artifactregistry.writer`, `roles/container.developer` — not `Owner`/`Editor`).
10. Wire GitHub Actions (`google-github-actions/auth`) to impersonate that Service Account via OIDC — confirm zero JSON keys exist anywhere in the repo or secrets store.

### Phase 4 — CI pipeline with security gates (Intermediate)
11. GitHub Actions workflow: checkout → dependency install → unit tests → **SAST** (CodeQL or Semgrep) → **SCA** (`pip-audit` or Snyk for Python deps) → **secrets scan** (gitleaks) → Docker build → **image scan** (Trivy, fail on HIGH/CRITICAL) → push to Artifact Registry.
12. Add a required-status-check so PRs can't merge if any scan fails.

### Phase 5 — Kubernetes deployment (Intermediate→Advanced)
13. Write Kubernetes manifests (or a Helm chart): Deployments, Services, resource requests/limits, liveness/readiness probes, HPA, per-tier NetworkPolicy.
14. Store DB credentials in **Secret Manager**, sync into cluster via **External Secrets Operator** (never plaintext Secrets in Git).
15. Add Ingress + **cert-manager** for automatic TLS (Let's Encrypt or Google-managed certs).
16. CD job deploys via `kubectl apply`/Helm using the same WIF-authenticated identity, scoped down further (`roles/container.developer` only, namespaced RBAC inside the cluster).

### Phase 6 — Observability (Advanced)
17. Install `kube-prometheus-stack` via Helm (Prometheus, Grafana, Alertmanager) in a dedicated `monitoring` namespace.
18. Add ServiceMonitors for each tier, build Grafana dashboards (request rate, latency, error rate, pod resource usage, DB connections).
19. Configure Alertmanager routes (Slack/email) for: pod crash-looping, high error rate, HPA maxed out, DB connection saturation.

### Phase 7 — Production hardening (Advanced)
20. Pod Security Standards (`restricted` profile), no root containers, read-only root filesystem where possible.
21. `PodDisruptionBudget` + multi-zone node pools for resilience.
22. Cost guardrails: GKE Autopilot cost allocation, budget alerts.
23. Backup/DR: Cloud SQL automated backups + point-in-time recovery tested at least once.
24. Runbook: documented rollback procedure (`kubectl rollout undo` / Helm rollback) and an on-call escalation doc.

### Phase 8 — Stretch goals (Expert)
25. Move CD to **GitOps** (ArgoCD or Flux) — GitHub Actions only builds and updates a manifest repo; ArgoCD reconciles the cluster.
26. **OPA/Gatekeeper** policies (deny `:latest` tags, require resource limits, deny privileged pods).
27. Progressive delivery (canary/blue-green) via Argo Rollouts.
28. Show Cloud Run as an alternate deploy target for one stateless component, to demonstrate the trade-off vs GKE.

---

## 6. Security tooling matrix

| Gate | Tool | Blocks on |
|---|---|---|
| Code (SAST) | CodeQL / Semgrep | Injection, insecure crypto, hardcoded secrets patterns |
| Dependencies (SCA) | `pip-audit` / Snyk | Known CVEs in Python packages |
| Secrets in git | gitleaks | Committed keys/tokens |
| Container image | Trivy | HIGH/CRITICAL OS + library CVEs |
| IaC | `trivy config` / Checkov | Public buckets, open firewall rules, missing encryption |
| Runtime policy | OPA/Gatekeeper | Non-compliant pod specs at admission time |

---

## 7. What "production-ready" adds beyond a typical demo

- No static credentials anywhere (OIDC/WIF only)
- Least-privilege IAM and namespaced K8s RBAC, not cluster-admin
- Terraform state remote + locked + versioned, environment-separated
- Secrets never in Git, always via Secret Manager
- TLS by default, no public DB IP
- Autoscaling + resource limits, not "it worked on my laptop"
- Alerting tied to actual on-call action, not dashboards nobody watches
- A tested rollback path

This phased structure lets you demo Phase 1–4 in an interview as "here's what I built" and describe Phases 5–8 as "here's how I'd take it further" — which is exactly how a senior DevOps engineer would talk about a real project.
