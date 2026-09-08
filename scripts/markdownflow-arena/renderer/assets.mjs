import { createHash } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { RenderError } from "./contract.mjs";

export async function loadAssetCache(filename) {
  const assets = new Map();
  if (!filename) return { assets };
  if ((await stat(filename)).size > 1_000_000)
    throw new RenderError("invalid_asset_cache");
  const bytes = await readFile(filename);
  const manifest = JSON.parse(bytes.toString("utf8"));
  if (
    manifest.version !== 1 ||
    !manifest.assets ||
    typeof manifest.assets !== "object" ||
    Array.isArray(manifest.assets)
  )
    throw new RenderError("invalid_asset_cache");
  let total = 0;
  for (const [url, entry] of Object.entries(manifest.assets)) {
    const parsed = new URL(url);
    if (
      parsed.protocol !== "https:" ||
      parsed.username ||
      parsed.password ||
      parsed.hash ||
      parsed.href !== url ||
      !entry ||
      typeof entry.path !== "string" ||
      !path.isAbsolute(entry.path) ||
      !/^[a-f0-9]{64}$/.test(entry.sha256 ?? "")
    )
      throw new RenderError("invalid_asset_cache");
    const size = (await stat(entry.path)).size;
    total += size;
    if (size > 20_000_000 || total > 100_000_000)
      throw new RenderError("asset_too_large");
    const body = await readFile(entry.path);
    if (createHash("sha256").update(body).digest("hex") !== entry.sha256)
      throw new RenderError("asset_cache_hash_mismatch");
    const contentType = body
      .subarray(0, 8)
      .equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
      ? "image/png"
      : body[0] === 255 && body[1] === 216 && body[2] === 255
        ? "image/jpeg"
        : null;
    if (!contentType) throw new RenderError("invalid_asset_cache_image");
    assets.set(url, { body, contentType });
  }
  return { assets, sha256: createHash("sha256").update(bytes).digest("hex") };
}

export function cachedImageForRequest(request, assets) {
  return request.method() === "GET" &&
    request.resourceType() === "image" &&
    !request.isNavigationRequest()
    ? assets.get(request.url())
    : undefined;
}
