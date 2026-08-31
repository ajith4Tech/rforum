# Deploying Rforum to k3s with Helm

This is the command sequence verified on a **shared single-node k3s**
host (Traefik already serving other Ingresses on 80/443, cert-manager
already installed). The chart lives at
[`deploy/helm/rforum/`](../deploy/helm/rforum/); see `values.yaml` for
every knob and `NOTES.txt` for what prints after install.

Helm talks to the cluster via kubeconfig. On k3s, always:

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
```

(`kubectl` may already work; Helm without this tries `localhost:8080` and
fails.)

Reference sizing in `values.yaml` is 4 vCPU / 8GB. Scale requests/limits
down on a smaller VM. On a busy shared node, confirm
`kubectl describe node` still has headroom before install.

## What this chart assumes

| Piece | Chart default | Notes |
|-------|---------------|--------|
| Ingress | class `traefik` | k3s bundled Traefik. Do **not** `--disable=traefik` and do **not** install ingress-nginx on the same 80/443. |
| TLS | Secret `rforum-tls` | cert-manager annotation on the Ingress; HTTP-01 solver must use class `traefik`. |
| Images | `rforum-backend:1.0.0`, `rforum-frontend:1.0.0` | Built locally, imported into k3s containerd (`imagePullPolicy: IfNotPresent`). |
| Backend UID | `runAsUser: 10001` | Matches `USER rforum` in `app/Dockerfile`. `runAsNonRoot` without a numeric UID fails `CreateContainerConfigError`. |
| Uvicorn | `--proxy-headers --forwarded-allow-ips='*'` | So FastAPI 307s stay on **https**. Missing this causes mixed-content blocks (`http://…/api/sessions/`) and a `/login` loop. |
| Migrations | Helm hook Job, `alembic upgrade heads` | Needs `SECRET_KEY` from the app Secret. `heads` (plural) because this repo has two Alembic branch tips. |

---

## 1. Install k3s (new VM only)

Skip if k3s is already running.

```bash
# Keep Traefik enabled — this chart's Ingress uses IngressClass "traefik".
curl -sfL https://get.k3s.io | sh -

sudo cat /var/lib/rancher/k3s/server/node-token   # only if you'll join other nodes later

mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
```

Confirm the context is this node (`kubectl config current-context`,
`kubectl get nodes`). Stop if it is not the cluster you intend.

## 2. Helm

```bash
curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3
chmod +x get_helm.sh
./get_helm.sh
helm version
```

## 3. Traefik (bundled)

The chart emits:

- Ingress `*-main` (`/` frontend, `/api` backend) and `*-ws` (`/ws`)
- Traefik `ServersTransport` (86400s on `/ws`, 60s on `/api`)
- Traefik `Middleware` buffering (`maxRequestBodyBytes` = 25MB)

Idle **entrypoint** timeout is still Traefik-global (default 180s). Raise
it once per cluster (brief Traefik restart — affects every Ingress on the
node):

```bash
kubectl apply -f - <<'EOF'
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: traefik
  namespace: kube-system
spec:
  valuesContent: |-
    additionalArguments:
      - "--entryPoints.web.transport.respondingTimeouts.idleTimeout=86400s"
      - "--entryPoints.websecure.transport.respondingTimeouts.idleTimeout=86400s"
EOF
```

On a single-node VM, Traefik's LoadBalancer is ServiceLB (Klipper) on
host 80/443.

## 4. cert-manager

Skip install if `kubectl get ns cert-manager` already exists. Match the
**existing** ClusterIssuer name (`kubectl get clusterissuer`) — this host
uses `letsencrypt-prod`, not `letsencrypt`.

Fresh cluster:

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo update
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager --create-namespace --set crds.enabled=true

kubectl apply -f - <<'EOF'
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt
spec:
  acme:
    email: you@example.com
    server: https://acme-v02.api.letsencrypt.org/directory
    privateKeySecretRef:
      name: letsencrypt-key
    solvers:
      - http01:
          ingress:
            class: traefik
EOF
```

Put the issuer name on the rforum overlay (step 7), not in git:

```yaml
ingress:
  host: rforum.example.com
  className: traefik
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt   # or letsencrypt-prod
  tls:
    enabled: true
    secretName: rforum-tls
```

## 5. Build and load images

From the repository root. No external registry.

```bash
docker build -f app/Dockerfile -t rforum-backend:1.0.0 .
docker build -f frontend/Dockerfile -t rforum-frontend:1.0.0 ./frontend

docker save rforum-backend:1.0.0  | sudo k3s ctr images import -
docker save rforum-frontend:1.0.0 | sudo k3s ctr images import -

sudo k3s ctr images list | grep rforum
```

Same-tag rebuilds need `kubectl -n rforum rollout restart deploy/rforum-backend`
(and frontend) because `imagePullPolicy` is `IfNotPresent`.

## 6. Secrets overlay (never commit)

Chart `secret.yaml` expects:

- DB Secret: `postgres-password`
- App Secret: `secret-key`, `super-admin-bootstrap-token`; plus
  `aws-access-key-id` / `aws-secret-access-key` when `storage.backend: s3`

`INVITE_CODE` and `S3_BUCKET` are ConfigMap/values, not Secret keys.

**Migrating an existing VM:** reuse `SECRET_KEY`, `INVITE_CODE`,
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET` (and region /
endpoint) from the backed-up `.env` so JWTs and S3 keep working. Generate
a **new** `POSTGRES_PASSWORD` — the dump does not need the old DB password.

```bash
# Example: source keys from a backup .env, new Postgres password
python3 - <<'PY'
# write /tmp/rforum-secrets.yaml (mode 600) — do not print values
...
PY
chmod 600 /tmp/rforum-secrets.yaml
```

Shape of `/tmp/rforum-secrets.yaml`:

```yaml
app:
  secretKey: "..."          # SECRET_KEY
  inviteCode: "..."         # INVITE_CODE
  superAdminEmail: ""       # optional
postgresql:
  auth:
    password: "..."         # fresh openssl rand -hex 20
storage:
  s3:
    bucket: "..."
    region: "eu-north-1"
    endpoint: ""            # or https://s3.eu-north-1.amazonaws.com
    accessKeyId: "..."
    secretAccessKey: "..."
ingress:
  host: rforum.t4gc.in
  className: traefik
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
```

Or pre-create Kubernetes Secrets and set `app.existingSecret` /
`postgresql.auth.existingSecret` (see `values.yaml` for key names).

`/tmp/rforum-secrets.yaml` is listed in `.gitignore` as
`values-migration.yaml` style — keep it off git either way.

## 7. Helm lint, then install

```bash
helm lint deploy/helm/rforum \
  --set postgresql.auth.password=lint-only \
  --set app.secretKey=lint-only \
  --set storage.s3.bucket=lint-bucket

helm upgrade --install rforum deploy/helm/rforum \
  --namespace rforum --create-namespace \
  -f deploy/helm/rforum/values.yaml \
  -f /tmp/rforum-secrets.yaml
```

Release name **`rforum`**, namespace **`rforum`**.

On a **fresh** install, Postgres/Redis/backend/frontend are submitted
first, then Alembic runs as a **post-install** hook. On later upgrades it
is a **pre-upgrade** hook. The Job and backend both `wait-for-postgres`.

`/api/health` does not touch the DB, so backend can show Ready a few
seconds before migrations finish on a first install.

**Restore-then-migrate:** if you will load a Postgres dump next, install
once with `migrations.enabled: false` in the overlay so the hook does not
create an empty schema you immediately overwrite. After restore, set it
back to `true` and `helm upgrade` (or leave it true if the dump already
includes `alembic_version` — `upgrade heads` is then a no-op).

## 8. Rollout checks

```bash
kubectl -n rforum get pods,svc,ingress,certificate,pvc
kubectl -n rforum get jobs -l app.kubernetes.io/component=migrate
kubectl -n rforum logs -l app.kubernetes.io/component=migrate --tail=80
```

Expect Postgres, Redis, backend, frontend `1/1 Running`. Ingress class
**traefik**, ADDRESS = node public IP. Certificate `rforum-tls` Ready.

If backend is `Init:CreateContainerConfigError` mentioning a non-numeric
user, the chart's `runAsUser: 10001` is missing from the live revision.

## 9. Restore production data (optional second pass)

Use a backup tree like `/root/rforum_db_backup`:

| File / dir | Restore? |
|------------|----------|
| `rforum_backup.dump` | Yes — custom-format `pg_restore` |
| `rforum_redis_backup.rdb` | Yes — onto the Redis PVC (often empty; still copy it) |
| `uploads/` | Yes — onto PVC `rforum-uploads`, chown **10001** |
| `.env` | Already applied as Helm secrets in step 6 |
| `frontend-build/`, `nginx/`, `systemd/` | **No** — Traefik + current images replace the old VM |

Keep the backend down or crash-looping during Postgres restore is fine;
do not run Alembic against an empty DB if you are about to `pg_restore --clean`.

### Postgres

```bash
kubectl -n rforum cp /path/to/rforum_backup.dump rforum-postgresql-0:/tmp/rforum_backup.dump
PGPASSWORD="$(kubectl -n rforum get secret rforum -o jsonpath='{.data.postgres-password}' | base64 -d)"
kubectl -n rforum exec rforum-postgresql-0 -- \
  env PGPASSWORD="${PGPASSWORD}" pg_restore \
    --clean --if-exists --no-owner --no-acl --exit-on-error \
    -U rforum -d rforum /tmp/rforum_backup.dump
kubectl -n rforum exec rforum-postgresql-0 -- rm -f /tmp/rforum_backup.dump
unset PGPASSWORD
```

`scripts/migration/restore_db.sh` is the same flags for Compose
port-forward; on k3s, `kubectl exec` as above is simpler.

Then `helm upgrade` with `migrations.enabled: true` so
`alembic upgrade heads` catches any revisions newer than the dump.

### Redis

Redis is started with AOF. To load an RDB, stop the pod, replace files,
start again:

```bash
kubectl -n rforum scale deploy/rforum-redis --replicas=0
kubectl -n rforum wait --for=delete pod -l app.kubernetes.io/component=redis --timeout=120s

# local-path volume, e.g.:
# /var/lib/rancher/k3s/storage/pvc-<uid>_rforum_rforum-redis
REDIS_PVC=$(kubectl -n rforum get pvc rforum-redis -o jsonpath='{.spec.volumeName}')
# Resolve host path from the PV, then:
#   rm -rf "$HOST/appendonlydir" "$HOST/dump.rdb"
#   cp rforum_redis_backup.rdb "$HOST/dump.rdb"
#   chown 999:999 "$HOST/dump.rdb"

kubectl -n rforum scale deploy/rforum-redis --replicas=1
```

### Uploads (local fallback)

```bash
# PV for claim rforum-uploads — mount is /data/uploads in the backend
rsync -a /path/to/backup/uploads/ "$UPLOADS_HOST_PATH/"
chown -R 10001:10001 "$UPLOADS_HOST_PATH"
```

New writes still go to S3 when `storage.backend: s3`; the PVC is the
read fallback (`app/storage/fallback.py`).

## 10. DNS

Point the hostname's `A`/`AAAA` at the VM public IP. Traefik already
binds 80/443.

## 11. Smoke test

```bash
curl -sI https://<host>/ | head -8          # 200, TLS from Let's Encrypt
curl -sk https://<host>/api/health
# {"status":"ok","service":"rforum","capabilities":{...}}

# Slash redirect must stay on https (mixed-content / login-loop check):
curl -sI https://<host>/api/sessions?limit=1 | grep -i location
# location: https://<host>/api/sessions/?limit=1
```

Log in (invite code from the overlay). Dashboard events/sessions lists
must not 307 to `http://`. Upload a presentation; confirm S3 or PVC
fallback. WebSocket: `wss://<host>/ws/<code>` (dedicated Ingress
`rforum-ws`).

```bash
websocat "wss://<host>/ws/does-not-exist"
# close 4404 = session not found — Upgrade reached the backend
```

## 12. Logs

```bash
kubectl -n rforum logs -l app.kubernetes.io/component=migrate --tail=200
kubectl -n rforum logs -l app.kubernetes.io/component=backend -c backend --tail=100
kubectl -n rforum logs -l app.kubernetes.io/component=frontend --tail=50
```

## 13. Load test

Run `rforum_500_user_load_test.js` **from another machine**. Watch
`kubectl top pods` / OOMKills. The 500-guest test was validated at
`backend.replicaCount: 1`.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|--------|-----|
| Helm `cluster unreachable` on `:8080` | Missing kubeconfig | `export KUBECONFIG=/etc/rancher/k3s/k3s.yaml` |
| Ingress 404 on the public hostname | Ingress class `nginx` while Traefik owns 80/443 | `ingress.className: traefik` |
| `CreateContainerConfigError` non-numeric user | `runAsNonRoot` without UID | Chart `runAsUser: 10001` |
| Migrate Job: `SECRET_KEY` Field required | Job only had ConfigMap | Chart mounts `secret-key` from the app Secret |
| Migrate Job: multiple Alembic heads | `alembic upgrade head` | Chart runs `upgrade heads` |
| Login loops; console mixed content `http://…/api/sessions/` | 307 Location uses http | Uvicorn `--proxy-headers --forwarded-allow-ips='*'` (already in the chart) |
| Certificate not issuing | HTTP-01 class ≠ Traefik | ClusterIssuer solver `class: traefik`; DNS A record to this node |
