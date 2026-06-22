#!/usr/bin/env node

import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "../../cook-web/node_modules/playwright/index.js";

const [, , inputPath, outputPath, viewportWidthArg] = process.argv;

if (!inputPath || !outputPath) {
  console.error("Usage: node render_pdf_html_card.mjs <input.html> <output.png> [viewportWidth]");
  process.exit(1);
}

const viewportWidth = Number.parseInt(viewportWidthArg || "1280", 10) || 1280;

const sourceHtml = await readFile(inputPath, "utf8");
const wrappedHtml = `<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <style>
      html, body {
        margin: 0;
        padding: 0;
        background: #ffffff;
      }
      body {
        display: inline-block;
      }
    </style>
  </head>
  <body>${sourceHtml}</body>
</html>`;

const browser = await chromium.launch({ headless: true });

try {
  const page = await browser.newPage({
    deviceScaleFactor: 2,
    viewport: {
      width: viewportWidth,
      height: 900,
    },
  });
  await page.setContent(wrappedHtml, { waitUntil: "load" });
  await page.evaluate(async () => {
    const fonts = document.fonts;
    if (fonts && fonts.ready) {
      await fonts.ready;
    }
  });

  const card = page.locator("body");
  await card.screenshot({
    path: outputPath,
    omitBackground: false,
  });
} finally {
  await browser.close();
}
