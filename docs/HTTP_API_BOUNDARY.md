# Local HTTP caller boundary

Fruth is a single-user loopback service. This contract protects the browser
channel. It does not authenticate arbitrary native processes, isolate OS users,
or make remote/multi-user deployment supported.

## Request admission and compatibility

Effectful `/api/` and `/v1/` requests require the exact header:

```http
X-Fruth-Action: 1
```

This covers POST/PUT/PATCH/DELETE, Responses aliases including
`/api/local_provider/<instance_id>/v1/responses`, multipart uploads, streaming,
preferences/settings/history/artifact mutations, lifecycle operations and
GET/HEAD with a true `refresh` query and `GET/HEAD /api/preview_saved_artifact`
preparation. Missing Origin is permitted for declared
native clients but does not waive the action header. Old native clients must
add it; request payloads and execution semantics are unchanged. Native processes
can freely supply the marker, so it is not an operator credential.

API Host must match a configured authority including its port. Defaults are
`127.0.0.1:5011`, `localhost:5011` and `[::1]:5011`. Browser Origin, when present,
must exactly equal `http://127.0.0.1:5011`, `http://localhost:5011` or
`http://[::1]:5011`. Null/opaque, empty, malformed and foreign origins are rejected
before route effects even with the marker. Scheme and port matter. Host and
forwarding headers cannot expand permission.

The trusted application setting `FRUTH_HTTP_ALLOWED_ORIGINS` is a list/tuple of
complete HTTP(S) origins without paths, credentials, queries or fragments. Host
authorities derive solely from it. An embedding deployment sets it before serving
requests; never populate it from request headers. Invalid configuration fails
closed. The default process still binds IPv4 loopback; permitted IPv6 authority
does not start an IPv6 listener. Remote exposure requires separate security work.

Matching-origin OPTIONS is passive and advertises the action, JSON and operator
headers. Ordinary API CORS permits only configured exact origins, including `/v1`;
foreign preflight is rejected. CORS is separate from effect admission: safelisted
forms/text and Origin-less browser GETs can reach a server without readable responses.

Admission errors contain string `error` and stable `error_code`:
`HTTP_HOST_NOT_ALLOWED` (400), `HTTP_ORIGIN_NOT_ALLOWED` (403), and
`HTTP_ACTION_REQUIRED` (403). The graph-rebase operator endpoint independently
requires its token, exact actor, durable evidence and compare-and-swap gates.

## GET inventory

| Surface | Behavior |
| --- | --- |
| running_instances, runtime_status, runtime_manifest/routing_table, backend_fabric, inference/agent_contract | Default cached observation needs no marker; explicit true `refresh` requires it before backend probes/status writes. |
| integrations/codex/status | Cached observation by default; explicit true `refresh` requires the marker before integration-status refresh. |
| available_models, backend_fabric `with_catalog`, available_models `with_limits` | Catalog/metadata reads retain their contract, including backend discovery where applicable; they do not execute inference or lifecycle mutations. |
| research, preferences, histories/events, settings lookup/list, Responses lookup, graph_rebase/readiness | Passive scoped/evidence-gated reads; projection caches confer no execution authority. |
| download_saved_artifact, view_saved_artifact | Confined artifact reads preserve script-free HTML/SVG security headers and download behavior. |
| preview_saved_artifact | Requires the action marker before preparing a preview, which may derive a flat response's exact dependency set into a bounded private temporary package. It does not register a durable artifact or execute response work. |
| preview_saved_artifact_wrapper/<signed-token>/<file> | Prepared navigation consumes the exact signed HTML/XHTML read capability. It cannot create a package or expand dependencies; existing wrapper CSP and mailto user-activation bridge remain. |
| preview_saved_artifact_assets, view_saved_artifact_assets | Confined asset reads retain wildcard read CORS for sandbox loading. Interactive assets retain HMAC/path/package/lease checks and opaque-origin CSP. The scoped read exception never admits ordinary API actions. Temporary lease bookkeeping stays in the preview owner. |

The marker never overrides file confinement, signed capabilities, start/provider
policies, budgets or runtime evidence gates.

Prepare an interactive preview using the existing `path`/`response_id` query and
the action marker. The HTML response retains its wrapper body and adds
`X-Fruth-Preview-Url`, a signed URL for ordinary navigation. The UI opens that
prepared URL after its admitted fetch. The header is exposed to permitted CORS
origins. Direct navigation to the preparation route without the marker is rejected;
do not move the marker into a query parameter or infer it from navigation headers.

## Preference bodies

`POST /api/inference_preferences` accepts JSON objects using `application/json`
or JSON-suffixed media types, including charset parameters. Existing object
updates and explicit `{}` reset remain valid. Rejections precede persistence and
leave existing preference bytes intact:

| Problem | Status / error_code |
| --- | --- |
| Unsupported/missing JSON media type | 415 / `PREFERENCES_UNSUPPORTED_MEDIA_TYPE` |
| Empty, whitespace-only, malformed or invalidly encoded JSON | 400 / `PREFERENCES_INVALID_JSON` |
| JSON null, array, string, number or boolean | 400 / `PREFERENCES_OBJECT_REQUIRED` |

Caller admission comes first; rejected foreign forms receive the caller error.

## Declared clients

The UI Axios transport marks same-origin API actions, including multipart and
refresh. Streaming Responses and native-fetch preferences/Codex status use the
same header helper. `fruthctl` and the conformance JSON HTTP client declare the
marker; passive monitors inherit that client without adding effects. Provider
direct transports retain their separate contracts.

Synced Codex providers routed through Fruth emit
`http_headers = { "X-Fruth-Action" = "1" }`; direct provider URLs do not. This uses
Codex's documented [fixed provider headers](https://developers.openai.com/codex/config-reference/).
Existing saved provider configurations need that field before sending actions
to the corrected runtime. A source change does not rewrite live configuration
or restart the service.

For a deliberate native preference reset:

```sh
curl --request POST http://127.0.0.1:5011/api/inference_preferences \
  --header 'X-Fruth-Action: 1' --header 'Content-Type: application/json' \
  --data '{}'
```

Use passive reads to check reachability; do not issue effects just to test a connection.
