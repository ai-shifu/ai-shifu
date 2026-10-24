#!/usr/bin/env node
import { randomBytes } from "node:crypto";
import { lookup } from "node:dns/promises";
import { createServer } from "node:http";
import { get as httpsGet } from "node:https";
import {
  readFile,
  mkdir,
  mkdtemp,
  rm,
  writeFile,
  chmod,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { cachedImageForRequest, loadAssetCache } from "./assets.mjs";
import { rendererTimeoutMs } from "./protocol.mjs";
import {
  classifyError,
  isAllowedAsset,
  isPublicAddress,
  MAX_PAGES,
  normalizeArtifact,
  normalizeAssetUrls,
  RenderError,
  RENDERER_VERSION,
} from "./contract.mjs";

const directory = path.dirname(fileURLToPath(import.meta.url));

function fetchAsset(url, address) {
  return new Promise((resolve, reject) => {
    // Pin the already checked public IP while keeping the hostname for TLS.
    // This avoids DNS rebinding and never sends or stores browser cookies.
    const request = httpsGet(
      url,
      {
        agent: false,
        headers: { Accept: "*/*", "Accept-Encoding": "identity" },
        lookup: (_host, options, callback) =>
          options.all
            ? callback(null, [address])
            : callback(null, address.address, address.family),
      },
      (response) => {
        if (response.statusCode !== 200) {
          response.destroy();
          reject(new RenderError("resource_load_failed"));
          return;
        }
        const chunks = [];
        let size = 0;
        response.on("data", (chunk) => {
          size += chunk.length;
          if (size > 20_000_000) {
            response.destroy(new RenderError("asset_too_large"));
            return;
          }
          chunks.push(chunk);
        });
        response.on("error", reject);
        response.on("end", () =>
          resolve({
            body: Buffer.concat(chunks),
            contentType:
              response.headers["content-type"] ?? "application/octet-stream",
            headers: {
              "access-control-allow-origin": "*",
              ...(response.headers["content-encoding"]
                ? { "content-encoding": response.headers["content-encoding"] }
                : {}),
            },
          }),
        );
      },
    );
    request.setTimeout(15000, () =>
      request.destroy(new RenderError("resource_timeout")),
    );
    request.on("error", reject);
  });
}

async function waitForReady(page, blocked, failed, pendingRequests) {
  await page.locator("#capture").waitFor({ state: "visible", timeout: 30000 });
  // Nested srcdoc documents can keep Playwright's aggregate load state busy
  // after every asset finishes. Check real request completion plus rendered
  // fonts, images, diagrams and stable frame geometry instead.
  // The renderer creates nested documents after the React commit. Wait for
  // fonts/images and three identical geometry snapshots across all frames.
  let previous;
  let stable = 0;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const states = await Promise.all(
      page.frames().map(async (frame) => {
        return frame.evaluate(async () => {
          await document.fonts.ready;
          const images = [...document.images];
          const broken = images.some(
            (img) => img.complete && img.naturalWidth === 0,
          );
          const pending = images.some((img) => !img.complete);
          const diagrams = [...document.querySelectorAll(".mermaid")];
          return {
            broken,
            pending,
            diagramPending: diagrams.some((node) => !node.querySelector("svg")),
            height: document.body?.scrollHeight,
            html: document.body?.innerHTML.length,
          };
        });
      }),
    );
    if (blocked.size) throw new RenderError("blocked_external_resource");
    if (failed.has("script")) throw new RenderError("script_failed");
    if (failed.size || states.some((state) => state.broken)) {
      throw new RenderError("resource_load_failed");
    }
    const signature = JSON.stringify(states);
    stable =
      signature === previous &&
      pendingRequests.size === 0 &&
      !states.some((state) => state.pending || state.diagramPending)
        ? stable + 1
        : 0;
    if (stable >= 3) return;
    previous = signature;
    await page.waitForTimeout(250);
  }
  throw new RenderError("render_not_ready");
}

async function slideCaptureTarget(page, width, height) {
  const scroller = page.locator("#capture .slide-stage__layer:visible");
  if ((await scroller.count()) !== 1)
    throw new RenderError("slide_scroller_missing");
  const target = { scroller, frame: page.mainFrame(), kind: "stage" };
  if ((await scroller.evaluate((node) => node.scrollHeight)) > height + 2)
    return target;
  for (const frame of page.frames()) {
    if (frame === page.mainFrame()) continue;
    const element = await frame.frameElement();
    const bounds = await element.boundingBox();
    await element.dispose();
    // A full-slide HTML sandbox can put scrolling on its own body or root.
    // Only that viewport is interchangeable with the outer Slide scroller;
    // model-authored inner containers remain subject to clipping checks.
    if (
      !bounds ||
      Math.abs(bounds.x) > 1 ||
      Math.abs(bounds.y) > 1 ||
      Math.abs(bounds.width - width) > 1 ||
      Math.abs(bounds.height - height) > 1
    )
      continue;
    const kind = await frame.evaluate(() => {
      const root = document.scrollingElement;
      if (root?.scrollHeight > innerHeight + 2) return "html";
      const body = document.body;
      if (
        body &&
        ["auto", "scroll"].includes(getComputedStyle(body).overflowY) &&
        body.scrollHeight > body.clientHeight + 2 &&
        Math.abs(body.clientHeight - innerHeight) <= 1
      )
        return "body";
      return null;
    });
    if (kind) return { scroller: frame.locator(kind), frame, kind };
  }
  return target;
}

async function assertNoClippedContent(page, mode, capture) {
  for (const frame of page.frames()) {
    const mainFrame = frame === page.mainFrame();
    if (!mainFrame) {
      const element = await frame.frameElement();
      const visible = await element.evaluate((node) => {
        const rect = node.getBoundingClientRect();
        return rect.width > 2 && rect.height > 2;
      });
      await element.dispose();
      if (!visible) continue;
    }
    const clipped = await frame.evaluate(
      ({ mainFrame, mode, capturedKind }) => {
        const onlyBackgroundOverflow = (node) => {
          if (
            [node, ...node.querySelectorAll("*")].some((child) =>
              ["::before", "::after"].some(
                (pseudo) =>
                  !["none", "normal"].includes(
                    getComputedStyle(child, pseudo).content,
                  ),
              ),
            )
          )
            return false;
          const bounds = node.getBoundingClientRect();
          const outside = (rect) =>
            rect.left < bounds.left - 1 ||
            rect.top < bounds.top - 1 ||
            rect.right > bounds.right + 1 ||
            rect.bottom > bounds.bottom + 1;
          const overflow = [...node.querySelectorAll("*")].filter((child) => {
            const rect = child.getBoundingClientRect();
            // SVG paint definitions have zero boxes at the document origin.
            // Do not extend this exception to rendered paths or stroked lines.
            if (
              child instanceof SVGElement &&
              child.closest(
                "defs, linearGradient, radialGradient, stop, marker",
              ) &&
              rect.width === 0 &&
              rect.height === 0
            )
              return false;
            return outside(rect);
          });
          if (
            !overflow.length ||
            !overflow.every((child) => {
              if (
                !(child instanceof HTMLDivElement) ||
                child.children.length ||
                child.textContent.trim() ||
                child.tabIndex >= 0 ||
                [...child.attributes].some((attr) =>
                  /^on|^(?:role|tabindex|contenteditable|draggable)$/i.test(
                    attr.name,
                  ),
                )
              )
                return false;
              const style = getComputedStyle(child);
              return (
                style.position === "absolute" &&
                style.pointerEvents === "none" &&
                /^blur\([\d.]+px\)$/.test(style.filter) &&
                style.filter !== "blur(0px)" &&
                style.backgroundImage === "none" &&
                style.boxShadow === "none" &&
                ["Top", "Right", "Bottom", "Left"].every(
                  (side) => parseFloat(style[`border${side}Width`]) === 0,
                ) &&
                ["::before", "::after"].every((pseudo) =>
                  ["none", "normal"].includes(
                    getComputedStyle(child, pseudo).content,
                  ),
                )
              );
            })
          )
            return false;
          // Empty blurred background shapes may intentionally cross a rounded
          // card's clipping edge. Never exempt overflowing text or other media.
          const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
          while (walker.nextNode()) {
            if (!walker.currentNode.textContent.trim()) continue;
            const range = document.createRange();
            range.selectNodeContents(walker.currentNode);
            if (
              [...range.getClientRects()].some(
                (rect) => rect.width > 0 && rect.height > 0 && outside(rect),
              )
            )
              return false;
          }
          return true;
        };
        const visibleEmojiFits = (node) => {
          // Emoji line boxes can exceed a centered figure while the entire
          // font bounding box still fits. Only exempt a single plain glyph;
          // other children, painted boxes and pseudo elements remain checked.
          if (node.children.length !== 1) return false;
          const child = node.firstElementChild;
          if (
            child.children.length ||
            [...node.childNodes].some(
              (item) =>
                item.nodeType === Node.TEXT_NODE && item.textContent.trim(),
            )
          )
            return false;
          const text = child.textContent;
          if (
            !/^\p{Extended_Pictographic}/u.test(text) ||
            [
              ...new Intl.Segmenter(undefined, {
                granularity: "grapheme",
              }).segment(text),
            ].length !== 1
          )
            return false;
          const childStyle = getComputedStyle(child);
          if (
            childStyle.transform !== "none" ||
            childStyle.filter !== "none" ||
            childStyle.textShadow !== "none" ||
            childStyle.boxShadow !== "none" ||
            childStyle.backgroundColor !== "rgba(0, 0, 0, 0)" ||
            childStyle.textDecorationLine !== "none" ||
            ["Top", "Right", "Bottom", "Left"].some(
              (side) => parseFloat(childStyle[`border${side}Width`]) !== 0,
            ) ||
            [node, child].some((element) =>
              ["::before", "::after"].some(
                (pseudo) =>
                  !["none", "normal"].includes(
                    getComputedStyle(element, pseudo).content,
                  ),
              ),
            )
          )
            return false;
          const range = document.createRange();
          range.selectNodeContents(child);
          const bounds = node.getBoundingClientRect();
          const left = bounds.left + node.clientLeft;
          const top = bounds.top + node.clientTop;
          const boxes = [...range.getClientRects()];
          return (
            boxes.length === 1 &&
            boxes.every(
              (box) =>
                box.left >= left &&
                box.top >= top &&
                box.right <= left + node.clientWidth &&
                box.bottom <= top + node.clientHeight,
            )
          );
        };
        const viewport = document.documentElement;
        // Full-page reading capture covers root vertical scrolling. Nested
        // documents and fixed slide viewports cannot expose that hidden tail.
        const root = document.scrollingElement ?? viewport;
        if (
          root.scrollWidth > window.innerWidth + 2 ||
          ((!mainFrame || mode === "slides") &&
            capturedKind !== "html" &&
            root.scrollHeight > window.innerHeight + 2)
        ) {
          return true;
        }
        return [...document.querySelectorAll("body, body *")].some((node) => {
          if (!(node instanceof HTMLElement)) return false;
          const rect = node.getBoundingClientRect();
          if (rect.width <= 2 || rect.height <= 2) return false;
          const style = getComputedStyle(node);
          if (style.visibility === "hidden" || style.display === "none")
            return false;
          const clips = (value) =>
            ["auto", "scroll", "hidden", "clip"].includes(value);
          // The trusted Slide component's outer scroller is captured below
          // in consecutive viewport-sized pages, without changing its layout.
          const capturedSlideScroller =
            capturedKind === "stage" &&
            mainFrame &&
            mode === "slides" &&
            node.matches("#capture .slide-stage__layer") &&
            ["auto", "scroll"].includes(style.overflowY);
          const capturedBody =
            capturedKind === "body" && node === document.body;
          const overflow =
            (!capturedSlideScroller &&
              !capturedBody &&
              clips(style.overflowY) &&
              node.scrollHeight > node.clientHeight + 2) ||
            (clips(style.overflowX) && node.scrollWidth > node.clientWidth + 2);
          return (
            overflow && !visibleEmojiFits(node) && !onlyBackgroundOverflow(node)
          );
        });
      },
      {
        mainFrame,
        mode,
        capturedKind: capture?.frame === frame ? capture.kind : null,
      },
    );
    if (clipped) throw new RenderError("content_clipped");
  }
}

export async function render(options) {
  let build;
  let chromium;
  try {
    ({ build } = await import("esbuild"));
    ({ chromium } = await import("@playwright/test"));
  } catch {
    throw new RenderError("renderer_dependencies_missing");
  }
  const artifact = normalizeArtifact(
    JSON.parse(await readFile(options.input, "utf8")),
  );
  const output = path.resolve(options.output);
  const timeout = rendererTimeoutMs(options["timeout-seconds"]);
  const assetCache = await loadAssetCache(options["asset-cache"]);
  const routePrefix = `/${randomBytes(24).toString("hex")}/`;
  if (options["asset-host"]?.length) {
    throw new RenderError("asset_host_allowlist_removed_use_exact_urls");
  }
  const allowedUrls = normalizeAssetUrls(options["asset-url"] ?? []);
  const allowedHosts = new Set(
    [...allowedUrls].map((value) => new URL(value).hostname),
  );
  const publicAddresses = new Map();
  for (const host of allowedHosts) {
    if (new URL(`https://${host}`).hostname !== host)
      throw new RenderError("invalid_asset_host");
    const addresses = await lookup(host, { all: true });
    if (
      !addresses.length ||
      addresses.some(({ address }) => !isPublicAddress(address))
    ) {
      throw new RenderError("private_asset_host");
    }
    publicAddresses.set(host, addresses[0]);
  }
  const temp = await mkdtemp(path.join(tmpdir(), "markdownflow-arena-"));
  let server;
  let browser;
  let deadline;
  let interrupted = false;
  const stop = () => {
    interrupted = true;
    void browser?.close().catch(() => {});
  };
  try {
    await mkdir(output, { recursive: true, mode: 0o700 });
    const bundle = await build({
      entryPoints: [path.join(directory, "client.jsx")],
      bundle: true,
      outdir: temp,
      write: false,
      format: "iife",
      define: { "process.env.NODE_ENV": '"production"' },
      loader: { ".woff2": "dataurl", ".woff": "dataurl", ".ttf": "dataurl" },
      logLevel: "silent",
      minify: true,
      // The library's nested peer dependencies must share the host React.
      alias: {
        react: path.join(directory, "../node_modules/react"),
        "react-dom": path.join(directory, "../node_modules/react-dom"),
      },
    });
    const files = new Map(
      bundle.outputFiles.map((file) => [
        path.basename(file.path),
        file.contents,
      ]),
    );
    const html = `<!doctype html><html><head><meta charset="utf-8"><title>Evaluation</title><link rel="stylesheet" href="${routePrefix}client.css"></head><body><div id="root"></div><script src="${routePrefix}client.js"></script></body></html>`;
    server = createServer((req, res) => {
      if (req.method !== "GET" || !req.url.startsWith(routePrefix)) {
        res.writeHead(404).end();
        return;
      }
      const filename = req.url.slice(routePrefix.length);
      if (filename && !files.has(filename)) {
        res.writeHead(404).end();
        return;
      }
      res.setHeader("Cache-Control", "no-store");
      res.setHeader("Referrer-Policy", "no-referrer");
      res.setHeader("X-Content-Type-Options", "nosniff");
      res.setHeader(
        "Content-Type",
        !filename
          ? "text/html"
          : filename.endsWith(".css")
            ? "text/css"
            : "text/javascript",
      );
      res.end(filename ? files.get(filename) : html);
    });
    await new Promise((resolve, reject) => {
      server.once("error", reject);
      server.listen(0, "127.0.0.1", resolve);
    });
    const origin = `http://127.0.0.1:${server.address().port}`;
    const rootUrl = `${origin}${routePrefix}`;
    browser = await chromium.launch({
      headless: true,
      chromiumSandbox: true,
      env: { PATH: process.env.PATH ?? "", LANG: "en_US.UTF-8" },
      ...(options["browser-path"]
        ? { executablePath: options["browser-path"] }
        : {}),
    });
    deadline = setTimeout(stop, timeout);
    process.once("SIGTERM", stop);
    process.once("SIGINT", stop);
    const width = 1280;
    const height = artifact.mode === "slides" ? 720 : 1600;
    const context = await browser.newContext({
      viewport: { width, height },
      deviceScaleFactor: 1,
      locale: artifact.locale,
      timezoneId: "UTC",
      colorScheme: "light",
      reducedMotion: "reduce",
      serviceWorkers: "block",
      acceptDownloads: false,
      permissions: [],
    });
    const pendingRequests = new Set();
    context.on("request", (request) => pendingRequests.add(request));
    context.on("requestfinished", (request) => pendingRequests.delete(request));
    context.on("requestfailed", (request) => pendingRequests.delete(request));
    const blocked = new Set();
    const failed = new Set();
    let entryLoaded = false;
    await context.routeWebSocket("**/*", (socket) => socket.close());
    await context.route("**/*", async (route) => {
      const request = route.request();
      const url = request.url();
      if (url === rootUrl && !entryLoaded && request.isNavigationRequest()) {
        entryLoaded = true;
        await route.continue();
        return;
      }
      const filename = url.startsWith(rootUrl)
        ? url.slice(rootUrl.length)
        : null;
      if (
        filename &&
        files.has(filename) &&
        request.method() === "GET" &&
        !request.isNavigationRequest()
      ) {
        await route.continue();
        return;
      }
      const cachedImage = cachedImageForRequest(request, assetCache.assets);
      if (cachedImage) {
        await route.fulfill({
          status: 200,
          ...cachedImage,
          headers: {
            "access-control-allow-origin": "*",
            "cache-control": "no-store",
          },
        });
        return;
      }
      if (isAllowedAsset(request, allowedUrls)) {
        try {
          const asset = await fetchAsset(
            url,
            publicAddresses.get(new URL(url).hostname),
          );
          await route.fulfill({ status: 200, ...asset });
        } catch {
          failed.add("asset");
          await route.abort();
        }
        return;
      }
      blocked.add(request.resourceType());
      await route.abort();
    });
    const page = await context.newPage();
    context.on("page", (popup) => {
      if (popup !== page) void popup.close();
    });
    page.on("dialog", (dialog) => void dialog.dismiss());
    page.on("pageerror", () => failed.add("script"));
    page.on("requestfailed", (request) => {
      if (
        !blocked.size &&
        ["image", "stylesheet", "font", "script"].includes(
          request.resourceType(),
        )
      )
        failed.add("asset");
    });
    await page.goto(rootUrl, { waitUntil: "load", timeout: 30000 });
    await page.waitForFunction(() => typeof window.renderArena === "function");
    const pages = [];
    for (let step = 0; step < artifact.stepCount; step += 1) {
      await page.evaluate(() => {
        document.body.style.minHeight = "";
        window.scrollTo(0, 0);
      });
      await page.evaluate(
        ({ artifact: data, step: index }) => window.renderArena(data, index),
        { artifact, step },
      );
      await waitForReady(page, blocked, failed, pendingRequests);
      const capture =
        artifact.mode === "slides"
          ? await slideCaptureTarget(page, width, height)
          : null;
      await assertNoClippedContent(page, artifact.mode, capture);
      const scroller = capture?.scroller;
      const contentHeight = await (
        artifact.mode === "slides" ? scroller : page.locator("#capture")
      ).evaluate((node) => node.scrollHeight);
      const count = Math.ceil(contentHeight / height);
      if (!count || count + pages.length > MAX_PAGES)
        throw new RenderError("too_many_pages");
      if (artifact.mode === "reading") {
        await page.evaluate((total) => {
          document.body.style.minHeight = `${total}px`;
        }, count * height);
      }
      for (let index = 0; index < count; index += 1) {
        let top = index * height;
        if (artifact.mode === "slides") {
          const requested = top;
          const actual = await scroller.evaluate((node, offset) => {
            node.scrollTop = offset;
            return node.scrollTop;
          }, requested);
          // At the end of a scroll range, Chromium clamps scrollTop. Crop
          // only the remaining tail and pad below with the page background,
          // so consecutive images neither omit nor duplicate content.
          top = requested - actual;
          await page.evaluate((total) => {
            document.body.style.minHeight = `${total}px`;
          }, height + top);
        }
        const target = path.join(
          output,
          `page-${String(pages.length + 1).padStart(3, "0")}.png`,
        );
        await page.screenshot({
          path: target,
          fullPage: true,
          clip: { x: 0, y: top, width, height },
          animations: "disabled",
        });
        await chmod(target, 0o600);
        pages.push(target);
      }
    }
    await context.close();
    // Print the captured pixels in a separate script-free document: iframe
    // printing and a final active slide cannot silently omit earlier pages.
    const printContext = await browser.newContext({ javaScriptEnabled: false });
    const printPage = await printContext.newPage();
    const images = await Promise.all(
      pages.map(
        async (filename) =>
          `<img src="data:image/png;base64,${(await readFile(filename)).toString("base64")}">`,
      ),
    );
    await printPage.setContent(
      `<!doctype html><html><head><title>Evaluation</title><style>@page{size:${width}px ${height}px;margin:0}html,body{margin:0}img{display:block;width:${width}px;height:${height}px;break-after:page}img:last-child{break-after:auto}</style></head><body>${images.join("")}</body></html>`,
    );
    const pdf = path.join(output, "complete.pdf");
    await printPage.pdf({
      path: pdf,
      printBackground: true,
      preferCSSPageSize: true,
    });
    await chmod(pdf, 0o600);
    const result = {
      status: "complete",
      pages,
      pdf,
      overview: pages[0],
      width,
      height,
      renderer_version: RENDERER_VERSION,
      markdownflow_ui_version: JSON.parse(
        await readFile(
          path.join(directory, "../node_modules/markdown-flow-ui/package.json"),
          "utf8",
        ),
      ).version,
      chromium_version: browser.version(),
      ...(assetCache.sha256 ? { asset_cache_sha256: assetCache.sha256 } : {}),
    };
    await writeFile(
      path.join(output, "render.json"),
      `${JSON.stringify(result, null, 2)}\n`,
      { mode: 0o600 },
    );
    return result;
  } catch (error) {
    if (interrupted) throw new RenderError("render_interrupted_or_timed_out");
    throw error;
  } finally {
    clearTimeout(deadline);
    process.removeListener("SIGTERM", stop);
    process.removeListener("SIGINT", stop);
    await browser?.close();
    if (server) await new Promise((resolve) => server.close(resolve));
    await rm(temp, { recursive: true, force: true });
  }
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  try {
    const { values } = parseArgs({
      options: {
        input: { type: "string" },
        output: { type: "string" },
        "asset-host": { type: "string", multiple: true },
        "asset-url": { type: "string", multiple: true },
        "asset-cache": { type: "string" },
        "browser-path": { type: "string" },
        "timeout-seconds": { type: "string" },
      },
    });
    if (!values.input || !values.output)
      throw new RenderError("missing_arguments");
    process.stdout.write(`${JSON.stringify(await render(values))}\n`);
  } catch (error) {
    process.stdout.write(
      `${JSON.stringify({ status: "failed", error_code: classifyError(error) })}\n`,
    );
    process.exitCode = 1;
  }
}
