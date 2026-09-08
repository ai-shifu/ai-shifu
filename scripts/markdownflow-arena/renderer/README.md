# MarkdownFlow arena renderer

This command runs the installed `markdown-flow-ui` production components in an
ephemeral Chromium profile. It does not start Cook Web, load `.env`, or expose a
product route. Use the same machine, package lock, and browser for an entire run.

Run these commands from `scripts/markdownflow-arena`:

```sh
npm ci
npx playwright install chromium
npm run render -- --input /absolute/artifact.json --output /absolute/render
```

Input is `{ "artifact_id": "opaque-id", "content": "...", "elements": [],
"metadata": { "locale": "zh-CN" } }`. `content` is required. Elements use the
existing ElementDTO `content`, `element_type` (or frontend `type`), `is_marker`, `is_new`, `is_renderable`, and
`sequence_number` fields. Preserve marker flags and sequence order from the
backend adapter. Audio and identity metadata are excluded from rendering.
The backend freezes the case's output language in `metadata.locale`. Supported
values are `zh-CN`, `en-US`, `fr-FR`, `ar-SA`, and `th-TH`; missing or unsupported
values default to `zh-CN`. The host document and both rendering components receive
the same language and direction: Arabic uses RTL and the other languages use LTR.

The slide-only evaluation pipeline rejects output without slide markers. The
underlying capture harness also supports general component regression fixtures:
plain output uses `ContentRender` with typing disabled. Output with marker
elements uses `Slide` and captures every marker step, preserving its cumulative
content and diff behavior. Reading pages are 1280 × 1600 pixels; slides are
1280 × 720 pixels. Long reading output and each scrollable slide are tiled
without dropping or repeating pixels, preserving the original scale and slide
boundaries. A tile boundary may cross a line of text. The PDF contains exactly those PNG pages;
its text is rasterized. Font appearance depends on installed CJK fonts.
Full-slide HTML sandbox root/body scrolling is paginated too. Clipping inside
other HTML iframes, fixed viewports, or model-authored nested scroll containers is
reported as `content_clipped` and excluded from comparisons. The tool does not
silently publish the visible portion of an incomplete HTML work.
An artifact may contain at most 50 PNG pages, including tiles across all marker
steps, bounding browser memory and the size of a local report. A 51st page fails the entire
artifact with `too_many_pages`; pages are never silently dropped.

The last stdout line is JSON with `status`, `pages` (absolute PNG paths), `pdf`,
`overview` (the first page), `width`, `height`, `renderer_version`,
`markdownflow_ui_version`, and `chromium_version`. Errors
return a nonzero status and `{ "status": "failed", "error_code": "..." }`,
without model content, raw errors, or model identity. Only a successful result
may be compared. Files are private and have neutral names.
Readiness requires all tracked requests to finish and each frame's fonts,
images, Mermaid diagrams, and geometry to stabilize. It does not depend on
Chromium's aggregate `networkidle` state for nested iframe documents.
`--timeout-seconds` sets the render deadline (default 300 seconds, allowed range
30–1200); the Python caller forwards the configured timeout to this option.

Outbound access is disabled by default. The trusted run configuration can pass
repeated `--asset-url https://cdn.example/fixed.png` flags to permit HTTPS GET requests for images,
fonts, stylesheets, and scripts from exact operator-approved URLs, including their paths and queries. Model output must
never supply this allowlist. A changed path or query is blocked even on an
approved hostname. The old `--asset-host` option fails closed; migrate each
needed asset to an explicit URL or the verified offline cache. Redirects, private destinations, API requests,
WebSockets, popups, downloads, and extra navigation are blocked. An unavailable
or blocked resource fails the artifact instead of producing an incomplete
comparison. HTML uses the library's iframe renderer inside the disposable
browser; never attach this renderer to a logged-in browser profile.

For original course images that require the operator's configured network
proxy, first cache the explicitly verified URLs without changing their bytes.
Pass `--asset-cache /absolute/private/assets.json` with this private format:

```json
{
  "version": 1,
  "assets": {
    "https://cdn.example/original.png": {
      "path": "/absolute/private/original.png",
      "sha256": "the 64 lowercase hexadecimal SHA256 characters"
    }
  }
}
```

Only exact GET image requests are fulfilled from verified PNG/JPEG bytes. The
cache never performs a network request, forwards cookies, permits scripts, or
widens the exact-URL/DNS rules. Files are limited to 20 MB each and
100 MB total. A changed hash or unsupported image fails the render. The result
records `asset_cache_sha256` for the cache manifest used. Keep the manifest and
images private and supply this option only from trusted run configuration.

Empty, inert, absolutely positioned blurred background shapes may intentionally
extend beyond a rounded card. Those shapes alone do not constitute missing
content; overflowing text, media, generated pseudo content, and interactive
elements still fail clipping checks.

`--browser-path /absolute/chromium` can select an installed Chromium. A matching
Playwright browser is preferred. In a restricted desktop sandbox, Chromium may
require permission to launch outside that sandbox; keep Chromium's own sandbox
enabled. The input/output files and the temporary HTTP server remain local.

Run `npm test` for boundary tests and `npm run smoke` for real
browser fixtures: long Chinese text, Mermaid, formula, SVG image, executable
HTML, multiple slide pages, scrollable slides, harmless emoji line-box overflow,
a blocked local-network image, and genuinely clipped HTML/emoji. Outputs go to a
temporary directory printed in the final JSON for visual inspection. Set
`ARENA_BROWSER_PATH` only when the default Playwright browser is unavailable.
Run `node renderer/locale.smoke.mjs` to verify all five locales
and RTL/LTR propagation through the installed reading and slide components.
