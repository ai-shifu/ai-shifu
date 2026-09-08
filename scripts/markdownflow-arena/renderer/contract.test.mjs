import assert from "node:assert/strict";
import { test } from "node:test";
import { createHash } from "node:crypto";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { cachedImageForRequest, loadAssetCache } from "./assets.mjs";
import {
  normalizeArtifact,
  MAX_PAGES,
  isAllowedAsset,
  isPublicAddress,
  classifyError,
} from "./contract.mjs";

test("passes only visual fields and removes identity, audio, and credentials", () => {
  const normalized = normalizeArtifact({
    content: "# Hello",
    artifact_id: "model-secret",
    metadata: { model: "model-secret", api_key: "secret" },
    elements: [
      {
        content: "# Hello",
        type: "text",
        is_marker: true,
        is_new: true,
        is_speakable: true,
        audio_url: "https://private.example/secret",
        element_bid: "model-secret",
        user_input: "private",
      },
    ],
  });
  assert.equal(normalized.mode, "slides");
  assert.equal(normalized.stepCount, 1);
  assert.equal(normalized.elements[0].is_new, true);
  assert.equal(normalized.elements[0].is_speakable, false);
  assert.equal(JSON.stringify(normalized).includes("secret"), false);
  assert.equal(JSON.stringify(normalized).includes("private"), false);
});

test("rejects empty artifacts and invalid elements", () => {
  assert.throws(() => normalizeArtifact({ content: " " }));
  assert.throws(() =>
    normalizeArtifact({ content: "# Hi", elements: [{ content: {} }] }),
  );
  assert.equal(normalizeArtifact({ content: "# Hi" }).mode, "reading");
});

test("accepts 50 slide pages and rejects 51 to match the attachment cell limit", () => {
  assert.equal(MAX_PAGES, 50);
  const artifact = (count) => ({
    content: "# Hi",
    elements: Array.from({ length: count }, () => ({
      content: "# Hi",
      is_marker: true,
    })),
  });
  assert.equal(normalizeArtifact(artifact(50)).stepCount, 50);
  assert.throws(() => normalizeArtifact(artifact(51)), {
    code: "too_many_pages",
  });
});

test("preserves every supported frozen locale and defaults unsupported values", () => {
  for (const locale of ["zh-CN", "en-US", "fr-FR", "ar-SA", "th-TH"]) {
    assert.equal(
      normalizeArtifact({ content: "# Hi", metadata: { locale } }).locale,
      locale,
    );
  }
  for (const locale of [undefined, null, "", "ar", "th", "de-DE"]) {
    assert.equal(
      normalizeArtifact({ content: "# Hi", metadata: { locale } }).locale,
      "zh-CN",
    );
  }
});

test("adapts production ElementDTO types to the Slide component contract", () => {
  const normalized = normalizeArtifact({
    content: "Production output",
    elements: [
      { content: "<div>Slide</div>", element_type: "html", is_marker: true },
      { content: "<svg/>", element_type: "svg", is_marker: true },
      { content: "Speech", element_type: "text", is_marker: false },
    ],
  });
  assert.deepEqual(
    normalized.elements.map((element) => element.type),
    ["html", "svg", "text"],
  );
  assert.equal(normalized.stepCount, 2);
});

test("external access is restricted to explicit HTTPS asset hosts and GET", () => {
  const request = (url, type = "image", method = "GET") => ({
    url: () => url,
    resourceType: () => type,
    method: () => method,
  });
  const hosts = new Set(["cdn.example"]);
  assert.equal(
    isAllowedAsset(request("https://cdn.example/a.png"), hosts),
    true,
  );
  for (const url of [
    "http://cdn.example/a",
    "https://cdn.example:444/a",
    "https://user:pass@cdn.example/a",
    "https://localhost/a",
    "file:///etc/passwd",
  ]) {
    assert.equal(isAllowedAsset(request(url), hosts), false);
  }
  assert.equal(
    isAllowedAsset(request("https://cdn.example/a", "fetch"), hosts),
    false,
  );
  assert.equal(
    isAllowedAsset(request("https://cdn.example/a", "image", "POST"), hosts),
    false,
  );
});

test("private destinations and raw errors cannot cross the renderer boundary", () => {
  for (const address of [
    "127.0.0.1",
    "10.2.3.4",
    "172.16.1.2",
    "192.168.1.1",
    "169.254.169.254",
    "::1",
    "::ffff:127.0.0.1",
    "fc00::1",
    "fe80::1",
  ]) {
    assert.equal(isPublicAddress(address), false);
  }
  assert.equal(isPublicAddress("8.8.8.8"), true);
  assert.equal(isPublicAddress("2606:4700:4700::1111"), true);
  assert.equal(classifyError(new Error("model secret")), "render_failed");
});

test("verified image cache matches only exact GET image requests", async (t) => {
  const directory = await mkdtemp(path.join(tmpdir(), "arena-assets-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const filename = path.join(directory, "image.png");
  const bytes = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jWZkAAAAASUVORK5CYII=",
    "base64",
  );
  await writeFile(filename, bytes);
  const url = "https://images.invalid/original.png";
  const manifest = {
    version: 1,
    assets: {
      [url]: {
        path: filename,
        sha256: createHash("sha256").update(bytes).digest("hex"),
      },
    },
  };
  const manifestPath = path.join(directory, "cache.json");
  await writeFile(manifestPath, JSON.stringify(manifest));
  const cache = await loadAssetCache(manifestPath);
  const request = (
    address = url,
    type = "image",
    method = "GET",
    navigation = false,
  ) => ({
    url: () => address,
    resourceType: () => type,
    method: () => method,
    isNavigationRequest: () => navigation,
  });
  assert.deepEqual(cachedImageForRequest(request(), cache.assets).body, bytes);
  for (const item of [
    request(url + "?other"),
    request(url, "script"),
    request(url, "image", "POST"),
    request(url, "image", "GET", true),
  ])
    assert.equal(cachedImageForRequest(item, cache.assets), undefined);
  await writeFile(filename, Buffer.from("changed private bytes"));
  await assert.rejects(loadAssetCache(manifestPath), {
    code: "asset_cache_hash_mismatch",
  });
  manifest.assets[url].sha256 = createHash("sha256")
    .update("changed private bytes")
    .digest("hex");
  await writeFile(manifestPath, JSON.stringify(manifest));
  await assert.rejects(loadAssetCache(manifestPath), {
    code: "invalid_asset_cache_image",
  });
});
