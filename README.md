# TechMart — 3-tier Python app on GKE (demo, production-shaped)

This repo is the companion code for the project blueprint. It contains every
file needed to run the pipeline end to end: app source, Terraform, Kubernetes
manifests, GitHub Actions CI/CD, and a Prometheus/Grafana monitoring layer.

## Repo map

```
app/frontend/        FastAPI frontend (HTML form + order list)
app/backend/          FastAPI backend (REST API + Postgres)
docker-compose.yml    Local dev — all 3 tiers on your laptop
terraform/            IaC: VPC, GKE Autopilot, Artifact Registry, Cloud SQL, WIF/IAM
k8s/                  Kubernetes manifests (base + dev overlay via Kustomize)
.github/workflows/    ci.yml (build/test/scan) and cd.yml (deploy to GKE)
monitoring/           kube-prometheus-stack values, ServiceMonitor, alert rules
```

---

## Step-by-step execution

### Step 0 — Prerequisites
- A GCP project with billing enabled
- `gcloud`, `terraform` (>=1.7), `kubectl`, `kustomize`, `docker`, `docker compose` installed locally
- A GitHub repo you own, pushed with this code

### Step 1 — Run it locally first (sanity check before touching cloud)
```bash
docker compose up --build
# frontend: http://localhost:8080
# backend:  http://localhost:8000/orders
```
Confirm you can place an order from the frontend and see it in the table.
This proves the app itself works before any cloud infra enters the picture.

### Step 2 — Enable required GCP APIs
```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable \
  container.googleapis.com \
  sqladmin.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  servicenetworking.googleapis.com \
  secretmanager.googleapis.com \
  cloudresourcemanager.googleapis.com
```

### Step 3 — Create the Terraform state bucket (once, manually)
```bash
gsutil mb -l us-central1 gs://YOUR_PROJECT_ID-tfstate
gsutil versioning set on gs://YOUR_PROJECT_ID-tfstate
```
Then edit `terraform/envs/dev/backend.tf` and replace
`REPLACE_WITH_YOUR_TFSTATE_BUCKET` with that bucket name.

### Step 4 — Configure Terraform variables
```bash
cd terraform/envs/dev
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: set project_id, region, github_repo (e.g. your-org/techmart-devops)
```

### Step 5 — Provision infrastructure
```bash
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```
This creates: VPC + private subnet + NAT, GKE Autopilot cluster,
Artifact Registry repo, Cloud SQL (Postgres, private IP, automated backups),
and the Workload Identity Federation pool + scoped service account.

Capture the outputs — you'll need them for GitHub:
```bash
terraform output
```

### Step 6 — Load the database schema
```bash
gcloud sql connect $(terraform output -raw cloudsql_connection_name | cut -d: -f3) \
  --user=techmart --database=techmart < ../../../app/backend/init.sql
```
(Password is in Secret Manager under the secret named in `terraform output`.)

### Step 7 — Configure GitHub repo variables (no secrets/keys needed)
In GitHub → Settings → Secrets and variables → Actions → **Variables** tab, add:
| Variable | Value |
|---|---|
| `GCP_PROJECT_ID` | your project id |
| `GCP_REGION` | e.g. `us-central1` |
| `GKE_CLUSTER_NAME` | from `terraform output gke_cluster_name` |
| `WORKLOAD_IDENTITY_PROVIDER` | from `terraform output workload_identity_provider` |
| `CI_SERVICE_ACCOUNT_EMAIL` | from `terraform output ci_service_account_email` |

No `GCP_SA_KEY` secret is created anywhere — that's the point of Step 5's WIF setup.

### Step 8 — Push to trigger CI
```bash
git add .
git commit -m "initial commit"
git push origin main
```
Watch the **Actions** tab: lint/test → SAST (CodeQL) → SCA (`pip-audit`) →
secrets scan (gitleaks) → IaC scan (`trivy config`) → Docker build → Trivy image scan
→ push to Artifact Registry. Any HIGH/CRITICAL CVE or exposed secret fails
the build before anything reaches the cluster.

### Step 9 — CD deploys automatically
On a successful CI run on `main`, `cd.yml` authenticates via the same WIF
identity, fetches GKE credentials, and runs:
```bash
kubectl apply -k k8s/overlays/dev
```
Before your first run, manually create the namespace once:
```bash
kubectl create namespace techmart-dev
kubectl create secret generic db-credentials -n techmart-dev \
  --from-literal=DB_HOST=$(terraform output -raw -state=terraform/envs/dev/terraform.tfstate cloudsql_private_ip 2>/dev/null || echo "SET_ME") \
  --from-literal=DB_NAME=techmart \
  --from-literal=DB_USER=techmart \
  --from-literal=DB_PASS=$(gcloud secrets versions access latest --secret=techmart-db-password)
```
(In Phase 5 of the blueprint, replace this manual secret step with the
External Secrets Operator syncing directly from Secret Manager.)

### Step 10 — Verify the deployment
```bash
kubectl get pods -n techmart-dev
kubectl get svc -n techmart-dev
kubectl get hpa -n techmart-dev
```

### Step 11 — Install monitoring
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install prometheus prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace \
  -f monitoring/prometheus-values.yaml

kubectl apply -f monitoring/servicemonitor-backend.yaml
kubectl apply -f monitoring/alert-rules.yaml
```
Access Grafana:
```bash
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80
# open http://localhost:3000 (user: admin, password: from prometheus-values.yaml)
```

### Step 12 — Expose it (optional, for a real domain + TLS)
Install `ingress-nginx` and `cert-manager` via Helm, point your domain's DNS
at the ingress IP, then apply `k8s/base/ingress.yaml` (already included via
the base kustomization) with your real hostname.

### Step 13 — Prove the rollback path (production-readiness check)
```bash
kubectl rollout undo deployment/backend -n techmart-dev
kubectl rollout status deployment/backend -n techmart-dev
```
Do this once deliberately so it's a tested procedure, not a hope.

---

## Versions pinned in this repo, and why

Checked and corrected against current releases as of Sept 2026:

| Component | Pinned to | Why |
|---|---|---|
| `hashicorp/google` provider | `~> 8.0` | Latest major (was on a stale v5 pin). **v6/v7/v8 include breaking changes** vs v5 — review the provider's upgrade guide before `terraform apply` on existing state. |
| Terraform CLI | `>= 1.9` | Current stable line. |
| GKE | Autopilot, `REGULAR` release channel | Google manages the node/control-plane version — no manual version pin needed or wanted. |
| Cloud SQL | `POSTGRES_17` | Latest GA major supported by Cloud SQL at time of writing (Postgres 18 exists upstream but wasn't yet the safe default for managed Cloud SQL). |
| App base image | `python:3.14-slim` | Matches the author's local dev version. `psycopg2-binary` ships prebuilt wheels for 3.14, so no compile-from-source surprises in the Docker build. |
| `actions/checkout` | `@v7` | Required alongside `auth@v3`; older majors lost support when GitHub removed Node 20 runners on **Sept 16, 2026**. |
| `actions/setup-python` | `@v6` | Same Node 20 removal — v5 is no longer usable. |
| `google-github-actions/auth` / `setup-gcloud` / `get-gke-credentials` | `@v3` | Current major, Node 24-compatible. |
| `github/codeql-action` | `@v4` | v3 is behind; v4 is current. |
| `gitleaks/gitleaks-action` | `@v3` | **v2 stopped working outright** once Node 20 runners were removed — this isn't optional. |
| `aquasecurity/trivy-action` | `@0.35.0` | **Security-critical fix:** tags `0.0.1`–`0.34.2` were compromised in a March 2026 supply-chain attack (credential-stealing malware, CVE-2026-33634). `0.35.0` is the first confirmed-safe tag. For production, pin to a full commit SHA instead of a tag — tags can still be force-moved. |
| `tfsec-action` | **removed, replaced** | tfsec is unmaintained; Aqua merged its entire check library into Trivy. The `iac-scan` job now runs `trivy-action` in `config` mode instead. |

If you're reading this well after Sept 2026, re-check each of these — especially the GitHub Actions majors, since GitHub's Node-version deprecations force real breakage, not just staleness warnings.

## Placeholders you must replace before running for real
- `REPLACE_WITH_YOUR_TFSTATE_BUCKET` in `terraform/envs/dev/backend.tf`
- `terraform.tfvars` values (copy from `.example`)
- `REGION`, `PROJECT_ID`, `IMAGE_TAG` in the k8s manifests (the CD workflow
  substitutes these automatically via `kustomize edit set image`)
- `techmart.example.com` in `k8s/base/ingress.yaml`
- Grafana admin password and Slack webhook in `monitoring/prometheus-values.yaml`
  (in real use, pull these from Secret Manager, don't commit plaintext)

## What's intentionally left as a next step (see blueprint Phase 5–8)
- External Secrets Operator instead of the manual `kubectl create secret` in Step 9
- ArgoCD/GitOps instead of `kubectl apply` from CI
- OPA/Gatekeeper policies
- Multi-environment promotion (dev → staging → prod) using `k8s/overlays/`
