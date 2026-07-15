# ACAS v2 Kubernetes Deployment

## Prerequisites

- Kubernetes 1.28+
- Helm 3.x (for PostgreSQL and Redis)
- kubectl configured with cluster access
- Container registry access (GHCR, GCR, ECR, etc.)
- cert-manager for TLS (optional, for ingress TLS)

## Quick Start

### 1. Build and Push Container Image

```bash
# Using the included Dockerfile.k8s (Debian-based, ~800MB)
docker build -t ghcr.io/<your-org>/acas:v2.0.0 -f deploy/k8s/Dockerfile.k8s .

# Or using multi-stage builder (smaller, ~150MB)
docker build -t ghcr.io/<your-org>/acas:v2.0.0 . --target builder

# Push to registry
docker push ghcr.io/<your-org>/acas:v2.0.0
```

### 2. Install PostgreSQL and Redis via Helm

```bash
# Add Bitnami Helm repo
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Install PostgreSQL
helm upgrade --install acas-postgres bitnami/postgresql \
  --namespace acas-prod --create-namespace \
  --set auth.database=acas \
  --set auth.username=acas \
  --set persistence.size=10Gi \
  --set persistence.storageClass=gp3 \
  --set resources.requests.cpu=250m,memory=256Mi \
  --set resources.limits.cpu=1000m,memory=1Gi

# Install Redis
helm upgrade --install acas-redis bitnami/redis \
  --namespace acas-prod \
  --set architecture=standalone \
  --set persistence.size=1Gi \
  --set resources.requests.cpu=100m,memory=128Mi \
  --set resources.limits.cpu=500m,memory=512Mi
```

### 3. Update Secrets

```bash
# Generate strong passwords
JWT_SECRET=$(openssl rand -base64 64)
DB_PASSWORD=$(openssl rand -base64 32)
APP_SECRET=$(openssl rand -base64 32)

# Update secret (base64 encode values)
kubectl create secret generic acas-secrets \
  --namespace acas-prod \
  --from-literal=ACAS_JWT_SECRET_KEY="$JWT_SECRET" \
  --from-literal=ACAS_DB_PASSWORD="$DB_PASSWORD" \
  --from-literal=ACAS_APP_SECRET_KEY="$APP_SECRET" \
  --dry-run=client -o yaml | kubectl apply -f -

# Update postgres secret (for Helm chart)
kubectl create secret generic acas-postgres-secret \
  --namespace acas-prod \
  --from-literal=postgres-password="$DB_PASSWORD" \
  --from-literal=password="$DB_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 4. Deploy ACAS v2

```bash
# Option A: Direct kubectl apply
kubectl apply -k deploy/k8s/

# Option B: Helm template + kubectl apply
helm template acas deploy/k8s | kubectl apply -f -

# Verify deployment
kubectl get pods -n acas-prod
kubectl get svc -n acas-prod
kubectl get hpa -n acas-prod
```

### 5. Run Alembic Migration

```bash
# Apply database migrations
kubectl exec -n acas-prod \
  $(kubectl get pod -n acas-prod -l app.kubernetes.io/name=acas-api -o jsonpath='{.items[0].metadata.name}') \
  -- python -m alembic upgrade head
```

## File Structure

```
deploy/k8s/
├── namespace.yaml       # Production namespace
├── configmap.yaml       # Non-sensitive config (env vars)
├── secret.yaml          # Sensitive config (passwords, keys)
├── deployment.yaml      # App deployment + service account
├── service.yaml         # ClusterIP service + headless
├── hpa.yaml            # Horizontal Pod Autoscaler
├── pdb.yaml            # Pod Disruption Budget
├── ingress.yaml        # Ingress with TLS + rate limiting
├── kustomization.yaml  # Kustomize orchestration
├── Dockerfile.k8s      # Debian-based image (use this, not root Dockerfile)
└── README.md           # This file
```

## Architecture

```
                    ┌─────────────────────┐
                    │  nginx-ingress       │
                    │  (TLS termination   │
                    │   rate limiting)     │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   acas-api Service  │
                    │   ClusterIP :8000   │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
    ┌─────▼─────┐       ┌─────▼─────┐       ┌─────▼─────┐
    │  acas-api │       │  acas-api │       │  acas-api │
    │  Pod #1   │       │  Pod #2   │       │  Pod #3   │
    └─────┬─────┘       └─────┬─────┘       └─────┬─────┘
          │                    │                    │
          └────────────────────┼────────────────────┘
                               │
              ┌────────────────┴────────────────┐
              │                                │
       ┌──────▼──────┐                  ┌──────▼──────┐
       │ PostgreSQL  │                  │   Redis     │
       │ (Bitnami)  │                  │  (Bitnami)  │
       └────────────┘                  └─────────────┘
```

## Scaling

```bash
# Manual scale
kubectl scale deployment acas-api --namespace acas-prod --replicas=10

# Auto-scale (HPA)
# HPA is configured with: min 2, max 20, target CPU 70%, target memory 80%
kubectl autoscale deployment acas-api \
  --namespace acas-prod \
  --min=2 --max=20 \
  --cpu-percent=70

# Check HPA status
kubectl get hpa -n acas-prod
```

## Monitoring

```bash
# Check pod logs
kubectl logs -n acas-prod -l app.kubernetes.io/name=acas-api -f

# Check metrics
kubectl port-forward -n acas-prod svc/acas-api 9090:9090 &
curl http://localhost:9090/metrics

# Check Prometheus targets (if Prometheus installed)
kubectl get servicemonitors -n acas-prod
```

## Troubleshooting

```bash
# Pod status
kubectl get pods -n acas-prod
kubectl describe pod -n acas-prod <pod-name>

# CrashLoopBackOff: check logs
kubectl logs -n acas-prod <pod-name> --previous

# Init container stuck: check DB/Redis connectivity
kubectl exec -n acas-prod <pod-name> -- nc -zv acas-postgres 5432
kubectl exec -n acas-prod <pod-name> -- nc -zv acas-redis 6379

# Readiness probe failing: check app logs
kubectl logs -n acas-prod <pod-name> | grep -i error
```

## Rollback

```bash
# Rollback deployment
kubectl rollout undo deployment/acas-api -n acas-prod

# Rollback to specific revision
kubectl rollout history deployment/acas-api -n acas-prod
kubectl rollout undo deployment/acas-api -n acas-prod --to-revision=<N>
```
