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

## MLX Whisper adapter

`scripts/mlx_whisper_server.py` has a separate, small native HTTP contract.
`POST /v1/audio/transcriptions` and `POST /api/transcribe` (including their
trailing-slash aliases) require `X-Fruth-Action: 1`, even without Origin. The
production caller `fruth_core.transports.whisper_transcribe` sends that marker.
`GET /healthz` remains passive and needs no marker, but checks Host and Origin.
Other implemented HTTP methods return 405; unknown methods retain the stdlib
handler's 501. Unknown GET/POST routes return 404 after caller admission.

Host must be a single permitted authority, including the **actual bound port**.
The allowed names are `127.0.0.1`, `localhost`, `::1` (bracketed in HTTP), the
explicit `--host` name/address and its bound address. Host comparison ignores
case. Port 80 additionally permits the normal omitted-port form. Other ports
must be explicit. The default bind remains `127.0.0.1`; allowing an IPv6 Host
does not create an IPv6 listener. Explicit `--host` and `--port` remain usable;
port 0 uses the assigned port. Wildcard binds (`0.0.0.0`, `::`, or empty) add no
wildcard authority: their allowlist remains the loopback names. To address a
specific non-loopback listener, configure that explicit bind name/address.
Forwarding headers cannot add authorities, and DNS resolution of a caller's Host
is never used for permission. This does not make remote deployment supported.

Origin, if present, must be a single exact `http://` origin built from those
lowercase authorities. Scheme and port matter; empty, `null`, foreign, malformed
and repeated origins fail. All responses omit CORS permission headers. OPTIONS
checks Host/Origin then returns 405, including local preflight; foreign preflight
is rejected without permission to submit. Fruth's UI uses the control plane, not
a browser CORS API on the Whisper port. Main-server origin configuration does
not configure the adapter.

The request must use `application/json` (media-type case is ignored; parameters
such as `charset=utf-8` are accepted), with UTF-8 JSON bytes, one positive decimal
Content-Length and no Transfer-Encoding. JSON-suffixed media types, forms,
multipart and plain text are not this adapter's format. The body must be an
object with `audio_path` as a nonempty UTF-8 string after trimming, without NUL.
Local paths remain intentional native inputs; this is not an upload API or a
filesystem confinement policy. Existing optional `language`, `task`, and
`word_timestamps` normalization, provider arguments and success fields (`text`,
`segments`, `language`, `model_path`) are preserved.

Admission runs before body parsing; framing/JSON/required-field checks run before
audio-path inspection or provider import/execution. Duplicate Host, Origin,
action, Content-Type or Content-Length headers fail closed. Caller failures use
the existing `HTTP_HOST_NOT_ALLOWED` (400), `HTTP_ORIGIN_NOT_ALLOWED` (403) and
`HTTP_ACTION_REQUIRED` (403) codes. Body errors contain string `error` plus:

| Problem | Status / error_code |
| --- | --- |
| Unsupported/missing media type | 415 / `WHISPER_UNSUPPORTED_MEDIA_TYPE` |
| Invalid framing, empty, malformed, invalidly encoded or excessively nested JSON | 400 / `WHISPER_INVALID_JSON` |
| Non-object JSON | 400 / `WHISPER_OBJECT_REQUIRED` |
| Invalid required path value or filesystem path error | 400 / `WHISPER_INVALID_AUDIO_PATH` |

A missing file retains its existing 400 `error`; provider exceptions retain 500
`{"error": "..."}` and the native client raises on HTTP failure. Rejected caller,
format and required-value requests do no audio-path access or transcription.
Host/Origin/action checks constrain browser-originated requests; arbitrary native
processes can supply these headers and are **not authenticated**. Protection does
not depend on browser-specific local-network restrictions. Direct HTTP fixture
results do not establish browser exploitability or broader security certification.
Existing processes need a later adapter restart and Fruth client-code reload to
activate both sides; editing these sources performs neither operation.
