# Helm chart simplification

Repo-only change on branch `helm-chart-simplification`. Verified with
`helm lint` and `helm template` diffs. **No `helm install` or `helm upgrade`
was run against any cluster.**

## What was removed and why

Each removal is a separate commit so it can be reverted on its own.

| Commit | Removed | Why |
|---|---|---|
| Remove unused backend HPA | `templates/backend-hpa.yaml`, `backend.autoscaling.*` | `enabled: false` in every values file; never rendered in prod |
| Remove backend PDB | `templates/backend-pdb.yaml`, `backend.podDisruptionBudget.*` | Single-replica backend; `maxUnavailable: 1` does not protect the pod |
| Remove frontend PDB | `templates/frontend-pdb.yaml`, `frontend.podDisruptionBudget.*` | Single-server deploy does not drain nodes; PDB is unused policy |
| Drop Traefik from Ingress | Traefik annotation branch, `ingress.controller` | Prod uses ingress-nginx only; class defaults to `nginx` |
| Drop external Postgres | `externalDatabase.*`, `postgresql.enabled`, helpers/templates gated on `enabled=false` | Bundled StatefulSet is the only supported mode |
| Drop external Redis | `externalRedis.*`, `redis.enabled`, REDIS_URL branches | Bundled Redis is the only supported mode |
| Drop SA annotation plumbing | `serviceAccount.annotations` template + values | Empty IRSA-style hook; ServiceAccount resource kept |
| Drop storageClassName overrides | optional `storageClass` on postgres/redis/uploads | Always empty → cluster default; field omitted so Kubernetes uses the default class |
| Require PVC persistence | emptyDir fallbacks and `persistence.enabled` toggles | Persistence was already true in every real deploy; emptyDir is not a supported mode for stateful data |
| Merge values | `values-production.yaml` deleted | Single `values.yaml` with production defaults; secrets still unset |

Also baked into `values.yaml` (were overlay-only or duplicated): image tags `1.0.0`, backend/frontend/postgres/redis resource sizes, PVC sizes (50Gi / 2Gi / 30Gi), `storage.backend: s3`, `ingress.tls` (`rforum-tls`), `frontend.replicaCount: 1` (was 3 in the overlay).

`docs/k3s-deploy.md` install commands were updated so they no longer reference the deleted overlay or Traefik `ingress.controller`.

## File counts

| | Before | After |
|---|---|---|
| Template files (`templates/`) | 18 | 15 |
| Values files | 2 (`values.yaml` + `values-production.yaml`) | 1 (`values.yaml`) |

Templates removed: `backend-hpa.yaml`, `backend-pdb.yaml`, `frontend-pdb.yaml`.

Templates kept: `_helpers.tpl`, `NOTES.txt`, `backend-deployment.yaml`, `backend-service.yaml`, `frontend-deployment.yaml`, `frontend-service.yaml`, `ingress.yaml`, `configmap.yaml`, `secret.yaml`, `serviceaccount.yaml`, `postgresql-statefulset.yaml`, `postgresql-service.yaml`, `redis.yaml`, `uploads-pvc.yaml`, `migration-job.yaml`. `Chart.yaml` unchanged.

## Rendered resource counts

Both renders used dummy `--set postgresql.auth.password=dummy --set app.secretKey=dummy` plus dummy S3 keys (required by `secret.yaml`; not committed).

Original: `helm template` with `-f values.yaml -f values-production.yaml` → **19 resources**.

New: `helm template` with `-f values.yaml` → **17 resources**.

| Resource | Before | After |
|---|---|---|
| PodDisruptionBudget `rforum-backend` | yes | **removed (intentional)** |
| PodDisruptionBudget `rforum-frontend` | yes | **removed (intentional)** |
| HorizontalPodAutoscaler | no (already disabled) | still absent |
| ServiceAccount `rforum` | yes | yes |
| Secret `rforum` (postgres password) | yes | yes |
| Secret `rforum-app` | yes | yes |
| ConfigMap `rforum-config` | yes | yes |
| PVC `rforum-redis` | yes | yes |
| PVC `rforum-uploads` | yes | yes |
| Service `rforum-backend` | yes | yes |
| Service `rforum-frontend` | yes | yes |
| Service `rforum-postgresql` | yes | yes |
| Service `rforum-redis` | yes | yes |
| Deployment `rforum-backend` | yes | yes |
| Deployment `rforum-frontend` | yes | yes (replicas 3 → **1**, intentional) |
| Deployment `rforum-redis` | yes | yes |
| StatefulSet `rforum-postgresql` (+ volumeClaimTemplate PVC) | yes | yes |
| Ingress `rforum-ws` | yes | yes (nginx annotations only) |
| Ingress `rforum-main` | yes | yes (nginx annotations only) |
| Job `rforum-migrate-1` | yes | yes |

**Silent disappearances:** none. The only resources present in the original render and missing afterward are the two PDBs, which were confirmed removals. HPA was already absent from the original render.

## `helm lint` / `helm template` diff summary

```
helm lint deploy/helm/rforum
# 1 chart(s) linted, 0 chart(s) failed
# [INFO] Chart.yaml: icon is recommended
# [INFO] missing postgresql.auth.password / app.secretKey — expected;
#        secrets are injected out-of-band, not baked into values.yaml
```

Unified diff of original vs new `helm template` output (79 lines) is exactly:

1. **Deleted** the two PDB manifests (`rforum-backend`, `rforum-frontend`).
2. **Changed** frontend Deployment `spec.replicas` from `3` to `1`.
3. **Comments only** on Ingress (`rforum-ws`): Traefik explanation dropped; same nginx timeout annotations and `ingressClassName: nginx`.
4. **Comments only** on the migrate Job: no longer mentions `postgresql.enabled`.

No other spec fields, names, selectors, volume mounts, env, or hook annotations changed.

## Keep-list confirmation

Nothing from the confirmed keep list was dropped:

- Postgres StatefulSet + PVC (volumeClaimTemplate) + Service — present
- Redis Deployment + PVC + Service — present
- Backend Deployment + Service — present
- Frontend Deployment + Service — present
- Both Ingress objects (WS + main), nginx class only — present
- Secret templates (postgres + app) — present
- ConfigMap — present
- Alembic migration Job — present
- Uploads PVC — present
- ServiceAccount resource (minus annotations) — present
- `storage.backend: s3` + S3 values + AWS secret keys (when `existingSecret` is unset) — present
- `_helpers.tpl`, `NOTES.txt`, `Chart.yaml` — present
