import { isIP } from "node:net";

export const RENDERER_VERSION = "3";
export const MAX_PAGES = 50;

export class RenderError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

export function normalizeArtifact(value) {
  if (!value || typeof value.content !== "string" || !value.content.trim()) {
    throw new RenderError("invalid_artifact");
  }
  if (Buffer.byteLength(value.content) > 5_000_000) {
    throw new RenderError("artifact_too_large");
  }
  if (value.elements !== undefined && !Array.isArray(value.elements)) {
    throw new RenderError("invalid_elements");
  }
  const elements = (value.elements ?? []).map((element, index) => {
    if (!element || typeof element.content !== "string") {
      throw new RenderError("invalid_element");
    }
    return {
      content: element.content,
      type:
        typeof element.type === "string"
          ? element.type
          : typeof element.element_type === "string"
            ? element.element_type
            : "text",
      sequence_number: element.sequence_number ?? index,
      is_marker: element.is_marker === true,
      is_new: element.is_new === true,
      is_renderable: element.is_renderable !== false,
      is_speakable: false,
      readonly: true,
    };
  });
  const markerCount = elements.filter((element) => element.is_marker).length;
  if (Buffer.byteLength(JSON.stringify(elements)) > 5_000_000) {
    throw new RenderError("artifact_too_large");
  }
  if (markerCount > MAX_PAGES) throw new RenderError("too_many_pages");
  return {
    content: value.content,
    elements,
    mode: markerCount ? "slides" : "reading",
    stepCount: markerCount || 1,
    locale: ["en-US", "fr-FR", "zh-CN", "ar-SA", "th-TH"].includes(
      value.metadata?.locale,
    )
      ? value.metadata.locale
      : "zh-CN",
  };
}

export function isPublicAddress(address) {
  if (isIP(address) === 4) {
    const [a, b, c] = address.split(".").map(Number);
    return !(
      a === 0 ||
      a === 10 ||
      a === 127 ||
      a >= 224 ||
      (a === 100 && b >= 64 && b <= 127) ||
      (a === 169 && b === 254) ||
      (a === 172 && b >= 16 && b <= 31) ||
      (a === 192 && b === 168) ||
      (a === 192 && b === 0) ||
      (a === 192 && b === 88 && c === 99) ||
      (a === 198 && b === 51 && c === 100) ||
      (a === 203 && b === 0 && c === 113) ||
      (a === 198 && (b === 18 || b === 19))
    );
  }
  if (isIP(address) === 6) {
    // Only global unicast addresses; exclude local and mapped IPv4 addresses.
    return (
      /^[23][0-9a-f]{3}:/i.test(address) &&
      !/^2001:db8:/i.test(address) &&
      !/^2002:/i.test(address)
    );
  }
  return false;
}

export function normalizeAssetUrls(values) {
  const urls = new Set();
  for (const value of values) {
    let url;
    try {
      url = new URL(value);
    } catch {
      throw new RenderError("invalid_asset_url");
    }
    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.hash ||
      (url.port && url.port !== "443")
    )
      throw new RenderError("invalid_asset_url");
    // Match Chromium's canonical request URL without broadening paths or queries.
    urls.add(url.href);
  }
  return urls;
}

export function isAllowedAsset(request, allowedUrls) {
  let url;
  try {
    url = new URL(request.url());
  } catch {
    return false;
  }
  return (
    request.method() === "GET" &&
    url.protocol === "https:" &&
    !url.username &&
    !url.password &&
    (!url.port || url.port === "443") &&
    allowedUrls.has(request.url()) &&
    !request.isNavigationRequest() &&
    ["image", "font", "stylesheet", "script"].includes(request.resourceType())
  );
}

export function classifyError(error) {
  return error instanceof RenderError ? error.code : "render_failed";
}
