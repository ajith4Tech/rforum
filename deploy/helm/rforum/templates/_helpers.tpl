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
Postgres connection details — resolves to either the bundled StatefulSet or
externalDatabase, depending on postgresql.enabled.
*/}}
{{- define "rforum.db.host" -}}
{{- if .Values.postgresql.enabled -}}
{{ include "rforum.postgresql.fullname" . }}
{{- else -}}
{{ .Values.externalDatabase.host }}
{{- end -}}
{{- end -}}

{{- define "rforum.db.port" -}}
{{- if .Values.postgresql.enabled -}}
5432
{{- else -}}
{{ .Values.externalDatabase.port }}
{{- end -}}
{{- end -}}

{{- define "rforum.db.name" -}}
{{- if .Values.postgresql.enabled -}}
{{ .Values.postgresql.auth.database }}
{{- else -}}
{{ .Values.externalDatabase.database }}
{{- end -}}
{{- end -}}

{{- define "rforum.db.user" -}}
{{- if .Values.postgresql.enabled -}}
{{ .Values.postgresql.auth.username }}
{{- else -}}
{{ .Values.externalDatabase.username }}
{{- end -}}
{{- end -}}

{{/* Name of the Secret holding the DB password, and the key within it */}}
{{- define "rforum.db.secretName" -}}
{{- if .Values.postgresql.enabled -}}
{{- if .Values.postgresql.auth.existingSecret -}}
{{ .Values.postgresql.auth.existingSecret }}
{{- else -}}
{{ include "rforum.fullname" . }}
{{- end -}}
{{- else -}}
{{- if .Values.externalDatabase.existingSecret -}}
{{ .Values.externalDatabase.existingSecret }}
{{- else -}}
{{ include "rforum.fullname" . }}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "rforum.db.secretKey" -}}
{{- if .Values.postgresql.enabled -}}
postgres-password
{{- else -}}
{{ .Values.externalDatabase.existingSecretPasswordKey }}
{{- end -}}
{{- end -}}

{{/* Redis host used to build REDIS_URL when the bundled Redis is enabled */}}
{{- define "rforum.redis.host" -}}
{{- if .Values.redis.enabled -}}
{{ include "rforum.redis.fullname" . }}
{{- else -}}
{{ .Values.externalRedis.host }}
{{- end -}}
{{- end -}}

{{/* Name of the Secret holding SECRET_KEY / AWS creds / REDIS_URL */}}
{{- define "rforum.app.secretName" -}}
{{- if .Values.app.existingSecret -}}
{{ .Values.app.existingSecret }}
{{- else -}}
{{ printf "%s-app" (include "rforum.fullname" .) }}
{{- end -}}
{{- end -}}
