{{/*
Expand the name of the chart.
*/}}
{{- define "rforum.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Full name: release-chart, capped at 63 chars.
*/}}
{{- define "rforum.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "rforum.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}

{{/*
Selector labels — stable across upgrades (no chart version).
*/}}
{{- define "rforum.selectorLabels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
