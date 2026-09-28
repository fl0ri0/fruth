# Security Policy

Fruth 0.1.3 is experimental, local-first software intended for one trusted
user on one machine.

## Local Boundary

The web control plane binds to `127.0.0.1` by default. Do not expose it through
a public interface, reverse proxy, tunnel, or shared host without a separate
security review and an authentication/authorization layer. Remote and
multi-user deployment are not supported in 0.1.3.

Runtime state, prompts, history, logs, and generated artifacts can contain
sensitive information. Keep the Fruth directory private and review files
before sharing them.

## Generated HTML Preview

Generated HTML is untrusted content. The ordinary saved-artifact view remains
non-interactive. The explicit HTML Preview uses a trusted wrapper around a CSP-
sandboxed iframe with an opaque origin: scripts may run, but they do not receive
Fruth's origin, forms, popups, ordinary top-navigation, workers, or external network access. Local
styles, scripts, images, media, and static `fetch()` dependencies are served
through a process-local signed read-only capability scoped to one portable
bundle (or one nested source-project directory). If a canonical response has
only flat artifacts, Fruth derives the exact response-owned dependency set into
a private temporary preview package; it does not register that package as an
artifact or persistent bundle. Temporary packages have an absolute lifetime and
bounded process-local storage, and restarting Fruth removes them and invalidates
their capabilities. Flat artifact buckets themselves are never interactive-
preview boundaries.

The sandbox permits browser-handled non-fetch protocols so a normal `mailto:`
link can reach the local mail handler. This capability covers the browser's
custom-protocol class, not only `mailto:`; popup targets remain blocked. It does
not grant generated code HTTP(S) top-navigation or broader network access.

Do not weaken this boundary by adding `allow-same-origin`, `unsafe-eval`, broad
`connect-src`, or cross-origin access to the ordinary saved-artifact route.

Saved SVG documents are also untrusted active content. Ordinary SVG views and
their asset/download responses carry a CSP sandbox with no script or same-origin
permission. Inline styles and embedded image/font data remain available for
rendering; network resources, forms and embedded browsing contexts are blocked.
This also covers `.svgz` and case-insensitive SVG extensions. The saved bytes
are unchanged. Downloading a file and opening it outside Fruth is a separate
browser/application trust boundary.

## Apple PCC Through Shortcuts

Apple PCC is a separate optional cloud backend. Starting its local adapter does
not start local model inference: selected task text, images and context are sent
to Apple when the user routes a request through the installed PCC Shortcuts.
The user installs and controls those Shortcuts; see the
[setup and sharing boundary](fruth_integrations/shortcuts/README.md).
Fruth does not sign into Apple accounts, change Apple Intelligence settings or
establish cloud access merely by observing a running local adapter. Provider
usage limits and refusals remain visible; automatic failover does not bypass
refusal or evidence gates. Local Apple AI is a separate on-device backend.

## ChatGPT Through Codex and Cloud Processing

Fruth stays local by default. The optional ChatGPT route is disabled until the
user explicitly enables the external connection. When ChatGPT is selected for
a turn, the prompt, context Fruth promotes for that turn, and only the local
files or Fruth artifacts explicitly selected for that turn leave the machine
and are processed by OpenAI.

Fruth:

- discovers a Codex executable and asks that executable for login status;
- does not read, copy, or persist provider credentials, OAuth tokens,
  keychain entries, or Codex authentication files;
- does not require a separate provider API key for this route;
- hands recognized images to Codex through its native image-input path;
- copies other selected regular files into a temporary per-request working
  directory configured read-only for the Codex run;
- accepts at most 5 selected files, up to 100 MiB each and 250 MiB in total,
  and rejects URLs, folders, and symbolic links;
- returns text output through this route;
- runs Codex ephemerally while ignoring project rules and user provider
  projections;
- does not set a fixed model.

The read-only setting describes the temporary working directory used for the
request; it is not a general remote- or multi-user-isolation guarantee. A
regular file being accepted also does not guarantee that the selected model
and its available tools can interpret that format semantically.

Review every selected file or artifact before sending it, and do not include
secrets in prompts or selected files. Disable the ChatGPT connection when cloud
processing is not intended. Normal request teardown removes the temporary
working copy; it does not delete the original Fruth artifact or make any claim
about deletion by the external service.

## Release Archives

Build archives only with `scripts/build_release_archive.py`. The builder uses
an explicit allowlist and excludes runtime state, logs, artifact contents,
caches, plans, hidden files, and the active model registry. It generates a
fresh empty registry, the standard empty artifact bucket structure, and
`MANIFEST.sha256`, then verifies the archive.

Every release candidate includes the reviewed Apache-2.0 `LICENSE`, `NOTICE`,
machine-readable citation metadata, project-participation policy, and
third-party notices. Publish mode
also fails closed until the changelog date is finalized and an explicit
release target is present. The builder never uploads an archive.
Verify-only also enforces named member-count, per-file, compressed-size, and
expanded-size safety bounds before extraction.

Never add credentials, private keys, environment files, personal runtime
state, or generated user artifacts to the source tree in order to make them
part of a release.

## Reporting a Vulnerability

Do not disclose a suspected vulnerability in a public issue. If the repository
offers GitHub private vulnerability reporting, use **Security > Report a
vulnerability**. Otherwise, preserve a minimal reproduction without user data
and use the public contact methods on
[@fl0ri0's GitHub profile](https://github.com/fl0ri0) only to request a private
channel. Do not include vulnerability details in that initial public contact.
