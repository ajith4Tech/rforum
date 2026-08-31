{{/*
Chart name
*/}}
{{- define "rforum.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Fully qualified app name
*/}}
{{- define "rforum.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "rforum.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "rforum.labels" -}}
helm.sh/chart: {{ include "rforum.chart" . }}
{{ include "rforum.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "rforum.selectorLabels" -}}
app.kubernetes.io/name: {{ include "rforum.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Per-component labels/selectors: pass (dict "root" . "component" "backend") */}}
{{- define "rforum.componentLabels" -}}
{{ include "rforum.labels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "rforum.componentSelectorLabels" -}}
{{ include "rforum.selectorLabels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "rforum.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "rforum.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/* Component fullnames */}}
{{- define "rforum.backend.fullname" -}}
{{- printf "%s-backend" (include "rforum.fullname" .) -}}
{{- end -}}

{{- define "rforum.frontend.fullname" -}}
{{- printf "%s-frontend" (include "rforum.fullname" .) -}}
{{- end -}}

{{- define "rforum.postgresql.fullname" -}}
{{- printf "%s-postgresql" (include "rforum.fullname" .) -}}
{{- end -}}

{{- define "rforum.redis.fullname" -}}
{{- printf "%s-redis" (include "rforum.fullname" .) -}}
{{- end -}}

{{/*
Image reference helpers — prepend image.registry (if set) to a
repository:tag pair.
*/}}
{{- define "rforum.backend.image" -}}
{{- printf "%s%s:%s" .Values.image.registry .Values.image.backend.repository .Values.image.backend.tag -}}
{{- end -}}

{{- define "rforum.frontend.image" -}}
{{- printf "%s%s:%s" .Values.image.registry .Values.image.frontend.repository .Values.image.frontend.tag -}}
{{- end -}}

{{/*
Postgres connection details — always the bundled StatefulSet.
*/}}
{{- define "rforum.db.host" -}}
{{ include "rforum.postgresql.fullname" . }}
{{- end -}}

{{- define "rforum.db.port" -}}
5432
{{- end -}}

{{- define "rforum.db.name" -}}
{{ .Values.postgresql.auth.database }}
{{- end -}}

{{- define "rforum.db.user" -}}
{{ .Values.postgresql.auth.username }}
{{- end -}}

{{/* Name of the Secret holding the DB password, and the key within it */}}
{{- define "rforum.db.secretName" -}}
{{- if .Values.postgresql.auth.existingSecret -}}
{{ .Values.postgresql.auth.existingSecret }}
{{- else -}}
{{ include "rforum.fullname" . }}
{{- end -}}
{{- end -}}

{{- define "rforum.db.secretKey" -}}
postgres-password
{{- end -}}

{{/* Redis host for REDIS_URL — always the bundled Service */}}
{{- define "rforum.redis.host" -}}
{{ include "rforum.redis.fullname" . }}
{{- end -}}

{{/* Name of the Secret holding SECRET_KEY / AWS creds / REDIS_URL */}}
{{- define "rforum.app.secretName" -}}
{{- if .Values.app.existingSecret -}}
{{ .Values.app.existingSecret }}
{{- else -}}
{{ printf "%s-app" (include "rforum.fullname" .) }}
{{- end -}}
{{- end -}}
