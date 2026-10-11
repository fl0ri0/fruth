Axios 1.20.0 browser distribution

The dashboard uses the unchanged official UMD browser build, served locally.
No package installation, runtime download, CDN fallback or build tool is needed.
The adjacent source map is retained unchanged for local debugging.

Upstream release: https://github.com/axios/axios/releases/tag/v1.20.0
Source commit: 84a9f3b9a4f3244b8c8e818f557d64c7b964fb25
Distribution: https://registry.npmjs.org/axios/-/axios-1.20.0.tgz
Metadata: https://registry.npmjs.org/axios/1.20.0
Distribution SHA256: 5aa2dc9a5d6ced926e4b6ca8ef8e0253b118867e240db8650c49379e972c12ac
Distribution integrity (verified against npm metadata):
sha512-r8aOh8j9cGKpgQAqpzrUHnSIc6a59Y3Xf/cv8sy1DrHCkZHzQGEuoq1tARk6qSyDdtQGSDgpb9kFlruzPvrgwg==

Files extracted without executing package scripts:
package/dist/axios.min.js -> axios.min.js (68,211 bytes)
SHA256: 7c433c881c3b0903317193a0dd5af714ce0f65cf77d5c7f067f18b96f0e8e2c7
package/dist/axios.min.js.map -> axios.min.js.map (267,025 bytes)
SHA256: 15fd3ff1dae38f059a7d7be7b7cc1fa641d7833f93b62a1832eb9c5fa4f62ad1
package/LICENSE -> LICENSE.txt (1,084 bytes)
SHA256: 82761059eaedacb3356803aea8a170d8298609f91b14fc32ee1bfb40d690183c

License: MIT; Copyright (c) 2014-present Matt Zabriskie & Collaborators.
The full upstream license is in LICENSE.txt. Axios is not relicensed under
Fruth's Apache-2.0 license. The npm package version/gitHead and LICENSE were
compared with the exact upstream GitHub tag. Generated dist files are supplied
by the npm distribution, not committed in that source tag. Registry integrity
is content verification; it is not a claim of independent signature verification.

Security review date: 2026-10-10.
Official advisory index: https://github.com/axios/axios/security/advisories
Relevant browser/core advisories include GHSA-j8rh-479h-cp32 (interceptor/header
inheritance), GHSA-x97p-jq2g-jp4f (form serialization), GHSA-9fr6-4gfg-395g
(default method), GHSA-vh66-26gq-q6x8 and GHSA-4hqw-qxg8-jxx2 (fetch/header
handling). Their published patched 1.x floor is 1.20.0. Earlier browser XSRF,
merge, cookie, JSON and form recursion advisories were also reviewed. Node-only
HTTP/proxy/HTTP2 findings do not establish a browser exploit. This dated review
does not guarantee that no future advisory will affect this fixed version.

For an upgrade, review the official release/advisory ranges, verify a new fixed
distribution against its metadata/tag, retain its exact bytes/license/digests,
update the dashboard path and packaging set, and run the affected browser,
caller-boundary and release checks. Google Fonts and Font Awesome remain remote.
