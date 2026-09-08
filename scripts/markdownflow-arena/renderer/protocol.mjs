import { RenderError } from "./contract.mjs";

export function rendererTimeoutMs(seconds = "300") {
  const value = Number(seconds);
  if (!Number.isInteger(value) || value < 30 || value > 1200)
    throw new RenderError("invalid_renderer_timeout");
  return value * 1000;
}

export function parseRendererOutput(stdout) {
  const line = stdout
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean)
    .at(-1);
  return JSON.parse(line ?? "");
}
