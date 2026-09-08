# MarkdownFlow arena renderer

This command runs the installed `markdown-flow-ui` production components in an
ephemeral Chromium profile. It does not start Cook Web, load `.env`, or expose a
product route. Use the same machine, package lock, and browser for an entire run.

```sh
npm ci
npx playwright install chromium
npm run arena:render -- --input /absolute/artifact.json --output /absolute/render
```

Input is `{ "artifact_id": "opaque-id", "content": "...", "elements": [],
"metadata": { "locale": "zh-CN" } }`. `content` is required. Elements use the
existing ElementDTO `content`, `element_type` (or frontend `type`), `is_marker`, `is_new`, `is_renderable`, and
`sequence_number` fields. Preserve marker flags and sequence order from the
backend adapter. Audio and identity metadata are excluded from rendering.

Plain output uses `ContentRender` with typing disabled. Output with marker
elements uses `Slide` and captures every marker step, preserving its cumulative
content and diff behavior. Reading pages are 1200 × 1600 pixels; slides are
1280 × 720 pixels. Long reading output and each scrollable slide are tiled
without dropping or repeating pixels, preserving the original scale and slide
boundaries. A tile boundary may cross a line of text. The PDF contains exactly those PNG pages;
its text is rasterized. Font appearance depends on installed CJK fonts.
Full-slide HTML sandbox root/body scrolling is paginated too. Clipping inside
other HTML iframes, fixed viewports, or model-authored nested scroll containers is
reported as `content_clipped` and excluded from comparisons. The tool does not
silently publish the visible portion of an incomplete HTML work.

The last stdout line is JSON with `status`, `pages` (absolute PNG paths), `pdf`,
`overview` (the first page), `width`, `height`, `renderer_version`,
`markdownflow_ui_version`, and `chromium_version`. Errors
return a nonzero status and `{ "status": "failed", "error_code": "..." }`,
without model content, raw errors, or model identity. Only a successful result
may be published or compared. Files are private and have neutral names.

Outbound access is disabled by default. The trusted run configuration can pass
repeated `--asset-host cdn.example` flags to permit HTTPS GET requests for images,
fonts, stylesheets, and scripts from exact public hostnames. Model output must
never supply this allowlist. Redirects, private destinations, API requests,
WebSockets, popups, downloads, and extra navigation are blocked. An unavailable
or blocked resource fails the artifact instead of producing an incomplete
comparison. HTML uses the library's iframe renderer inside the disposable
browser; never attach this renderer to a logged-in browser profile.

`--browser-path /absolute/chromium` can select an installed Chromium. A matching
Playwright browser is preferred. In a restricted desktop sandbox, Chromium may
require permission to launch outside that sandbox; keep Chromium's own sandbox
enabled. The input/output files and the temporary HTTP server remain local.

Run `npm run arena:test` for boundary tests and `npm run arena:smoke` for real
browser fixtures: long Chinese text, Mermaid, formula, SVG image, executable
HTML, multiple slide pages, scrollable slides, harmless emoji line-box overflow,
a blocked local-network image, and genuinely clipped HTML/emoji. Outputs go to a
temporary directory printed in the final JSON for visual inspection. Set
`ARENA_BROWSER_PATH` only when the default Playwright browser is unavailable.
