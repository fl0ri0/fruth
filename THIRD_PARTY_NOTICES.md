# Third-Party Components

Fruth's own source code and project documentation are licensed under the
Apache License 2.0. Third-party components keep their own licenses.

## Bundled with the Source Distribution

### Montserrat Black

The standalone project page includes a local Latin webfont subset of
Montserrat Black at weight 900.

- Copyright 2024 The Montserrat.Git Project Authors
- Source: <https://github.com/JulietaUla/Montserrat.git>
- License: SIL Open Font License 1.1
- License text: [`site/fonts/OFL.txt`](site/fonts/OFL.txt)
- Provenance and file hash: [`site/fonts/README.md`](site/fonts/README.md)

Montserrat is not relicensed under Apache-2.0.

## Installed Separately

Python packages installed through `requirements.txt`, local AI runtimes,
model weights, and models are not bundled with Fruth. They remain subject to
their respective upstream licenses and terms.

### Apple Foundation Models

Apple FM integration uses the Mac's installed `fm` command and Apple-managed
system model. Neither is bundled with Fruth. Fruth checks availability and license
status but does not accept Apple's terms, download models or enable Apple
Intelligence on the user's behalf. No Python Foundation Models SDK is required.

The optional Apple PCC bridge uses the Mac's installed Shortcuts application and
user-installed Shortcuts to access Apple's cloud models. Neither Shortcuts nor
Apple's models or frameworks are bundled in the source archive.

### PDF extraction and rendering

- `pypdf` extracts existing text layers. Its upstream license is
  [BSD-3-Clause](https://github.com/py-pdf/pypdf/blob/main/LICENSE).
- On macOS, `pyobjc-framework-Quartz` exposes Apple's PDFKit, CoreGraphics and
  ImageIO frameworks for page rendering. The binding and its `pyobjc-core` and
  `pyobjc-framework-Cocoa` dependencies use the
  [PyObjC MIT license](https://github.com/ronaldoussoren/pyobjc/blob/main/pyobjc-core/License.txt).
  Upstream distributions also carry notices for embedded components such as
  libffi; preserve the notices shipped with the installed packages if bundling
  them in a downstream distribution.
- Apple's frameworks are provided by macOS, under Apple's applicable
  [system software terms](https://www.apple.com/legal/sla/).
  They are not bundled in Fruth's source archive.

These Python packages are installed separately through `requirements.txt`;
their code and binary wheels are not included in Fruth's source distribution.

## Loaded at Runtime from External CDNs

The current dashboard requests Google Fonts, Axios, and Font Awesome from
their upstream CDNs when the dashboard is opened with network access. The
architecture diagram requests JetBrains Mono from Google Fonts. These
resources are not bundled in the Fruth source archive and remain under their
respective upstream licenses and terms.

The standalone repository landing page under `site/` does not make those
requests; its display font is bundled locally with the license and provenance
described above.
