# Deploying Rforum to k3s with Helm

This is the exact command sequence for a fresh Ubuntu VM. The chart lives at
[`deploy/helm/rforum/`](../deploy/helm/rforum/); see that directory's
`values.yaml` for every configurable knob and `NOTES.txt` for what prints
after install.

Reference VM: 4 vCPU / 8GB (double the 2 vCPU / 3.7GB host the 500-guest k6
load test was validated against — see `values-production.yaml`). Scale
`values-production.yaml` down if your VM is smaller.

## 1. Install k3s

```bash
# Traefik is disabled — this chart's Ingress is tuned for ingress-nginx
# (see "Why ingress-nginx, not Traefik" below). If you'd rather keep
# Traefik, drop --disable=traefik and set ingress.controller=traefik when
# installing the chart later.
curl -sfL https://get.k3s.io | sh -s - --disable=traefik

sudo cat /var/lib/rancher/k3s/server/node-token   # only if you'll join other nodes later
```

k3s installs `kubectl` at `/usr/local/bin/kubectl` and writes a kubeconfig to
`/etc/rancher/k3s/k3s.yaml`. For a non-root shell:

```bash
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config
```

## 2. Verify the node

```bash
kubectl get nodes
# NAME     STATUS   ROLES                  AGE   VERSION
# vm-host  Ready    control-plane,master   1m    v1.30.x+k3s1
```

## 3. Install Helm

```bash
curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3
chmod +x get_helm.sh
./get_helm.sh
helm version
```

## 4. Install ingress-nginx

### Why ingress-nginx, not Traefik

k3s ships Traefik by default, but this app's WebSocket path
(`/ws/{session_code}`) needs an 86400s proxy read timeout and `/api/`
(presentation uploads) needs a 25MB body limit — exactly what the current
bare-metal `nginx.conf` already enforces (see `docs/ARCHITECTURE.md` §9).
ingress-nginx exposes both as plain per-Ingress annotations
(`nginx.ingress.kubernetes.io/proxy-read-timeout`,
`.../proxy-body-size`) — a direct, auditable translation of the existing
config. Traefik has no equivalent per-Ingress-object timeout annotation
(it's a static/dynamic entrypoint setting), so the same tuning would require
a k3s-specific `HelmChartConfig` resource instead. Both paths are supported
by the chart (`ingress.controller: nginx|traefik`); this doc uses nginx.

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  --set controller.ingressClassResource.name=nginx \
  --set controller.service.type=LoadBalancer
```

On a single-node k3s VM, `LoadBalancer` is satisfied by k3s's bundled
ServiceLB (Klipper) and simply binds host ports 80/443.

## 5. Build and load application images

Run from the repository root (`/home/ubuntu/rforum` or wherever you cloned
it). No external registry is required — images are imported directly into
k3s's embedded containerd.

```bash
docker build -f app/Dockerfile -t rforum-backend:1.0.0 .
docker build -f frontend/Dockerfile -t rforum-frontend:1.0.0 ./frontend

docker save rforum-backend:1.0.0  | sudo k3s ctr images import -
docker save rforum-frontend:1.0.0 | sudo k3s ctr images import -

# Confirm both landed in containerd's local image store:
sudo k3s ctr images list | grep rforum
```

If you rebuild an image, re-run the two `docker save | k3s ctr images
import` lines and then `kubectl rollout restart deployment/...` (imagePullPolicy
is `IfNotPresent`, so a same-tag rebuild needs an explicit restart to pick up
the new layer — or bump the tag and `helm upgrade` instead).

## 6. Create the namespace

```bash
kubectl create namespace rforum
```

## 7. Create production secrets

Don't put real secrets in a committed values file. Generate a `SECRET_KEY`
and a Postgres password, then pass them at install time (or in a
gitignored local file):

```bash
SECRET_KEY=$(openssl rand -hex 32)
PG_PASSWORD=$(openssl rand -hex 20)

cat > /tmp/rforum-secrets.yaml <<EOF
app:
  secretKey: "${SECRET_KEY}"
  inviteCode: "$(openssl rand -hex 6)"
postgresql:
  auth:
    password: "${PG_PASSWORD}"
EOF
chmod 600 /tmp/rforum-secrets.yaml
```

If you're using S3 storage (`storage.backend: s3`), add AWS credentials to
the same file:

```yaml
storage:
  s3:
    accessKeyId: "AKIA..."
    secretAccessKey: "..."
```

(Or skip both keys entirely and rely on an IAM instance profile attached to
the VM — `app/storage/s3.py` falls back to boto3's default credential chain
when they're blank.)

Alternatively, pre-create your own Kubernetes Secrets and point
`app.existingSecret` / `postgresql.auth.existingSecret` at them instead —
see `values.yaml` for the expected keys.

## 8. Configure `values-production.yaml`

Edit `deploy/helm/rforum/values-production.yaml`:

- `ingress.host` → your real hostname (replaces `rforum.example.com`)
- `storage.s3.bucket` / `storage.s3.region` if using S3 storage; otherwise
  delete the `storage:` block from this overlay to keep the local-PVC
  default from `values.yaml`
- `image.backend.tag` / `image.frontend.tag` if you didn't build `1.0.0`

## 9. Install

```bash
helm upgrade --install rforum deploy/helm/rforum \
  --namespace rforum \
  -f deploy/helm/rforum/values-production.yaml \
  -f /tmp/rforum-secrets.yaml
```

On a fresh install, Postgres/Redis/backend/frontend are all submitted as
normal resources first, then the Alembic migration Job runs as a
**post-install** hook (not pre-install — the bundled Postgres StatefulSet
doesn't exist yet during a pre-install hook, so migrations can't run before
it; see the comment in `templates/migration-job.yaml`). On later `helm
upgrade` runs, migrations run as a **pre-upgrade** hook instead, before the
upgrade's changes apply — by then Postgres is already up from the prior
release. Both the migration Job and backend pods carry a `wait-for-postgres`
initContainer so they don't fail outright if Postgres takes a few extra
seconds to accept connections after being created.

One consequence on a fresh install: backend pods can start and report
Ready (`/api/health` doesn't check the database) slightly before migrations
finish, so the very first requests in that brief window may 500. This is
self-healing (no crash-loop) and only affects the first install of a
release with no existing traffic.

## 10. Check rollout

```bash
kubectl -n rforum get pods
kubectl -n rforum get svc
kubectl -n rforum get ingress
```

All pods should reach `Running`/`1/1` or `2/2` Ready. Check the migration
Job specifically — `kubectl -n rforum get jobs` — and confirm it reached
`Complete` rather than assuming pod-Ready implies migrations finished.

## 11. View logs

```bash
kubectl -n rforum logs -l app.kubernetes.io/component=migrate --tail=200
kubectl -n rforum logs -l app.kubernetes.io/component=backend -f
kubectl -n rforum logs -l app.kubernetes.io/component=frontend -f
```

## 12. Migrations

Already run automatically by step 9 (Helm `post-install`/`pre-upgrade` hook —
see `templates/migration-job.yaml`). To re-run manually against a live
release without a full upgrade:

```bash
helm upgrade rforum deploy/helm/rforum -n rforum \
  -f deploy/helm/rforum/values-production.yaml -f /tmp/rforum-secrets.yaml
```

## 13. Configure DNS

Point your domain's `A`/`AAAA` record at the VM's public IP. k3s's
ServiceLB binds the ingress-nginx LoadBalancer Service directly to host
ports 80/443, so no additional cloud load balancer is needed for a
single-node deployment.

## 14. Configure HTTPS

Two options:

**cert-manager (recommended, automatic renewal):**

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
            ingressClassName: nginx
EOF
```

Then add to your values file:

```yaml
ingress:
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt
  tls:
    enabled: true
    secretName: rforum-tls
```

and `helm upgrade` again.

**Or reuse existing certs** (e.g. copied from the current
`rforum.t4gc.in` Let's Encrypt certs): create the TLS secret directly and
just set `ingress.tls.enabled: true` / `ingress.tls.secretName`:

```bash
kubectl -n rforum create secret tls rforum-tls \
  --cert=fullchain.pem --key=privkey.pem
```

## 15. Verify the frontend

```bash
curl -sk https://<your-host>/ | head -20        # SvelteKit index.html
```

## 16. Verify the API

```bash
curl -sk https://<your-host>/api/health
# {"status":"ok","service":"rforum","capabilities":{...}}
```

## 17. Verify the WebSocket

```bash
# Any WS client works; a quick smoke test with websocat:
websocat "wss://<your-host>/ws/does-not-exist"
# Expect an immediate close with code 4404 (session not found) — confirms
# the Ingress is passing the Upgrade handshake through to the backend Service.
```

## 18. Verify presentation upload + interactive slides

Log in through the UI (register with the `app.inviteCode` you set in step
7), create an event/session, upload a PDF/PPTX, and confirm page images
render and a poll/QNA slide accepts responses live. This exercises the
storage backend (local PVC or S3), LibreOffice conversion, and the Redis
pub/sub broadcast path end-to-end.

## 19. Run the existing 500-user k6 load test

Run `rforum_500_user_load_test.js` **from a separate machine**, not from
the cluster's node — see the load-test's own header comments for required
env vars (moderator invite code, target host). Do not run it from this k3s
host itself if it's small; validate capacity incrementally and watch
`kubectl top pods` / `kubectl -n rforum get pods` for OOMKills or restarts
during the run.
