# Screens (HTML visuals) for a plain renderer

The host has no preloaded libraries. Keep helpful visuals simple and self-contained:

- Use one root `<div>` with inline styles; no external assets, frameworks or scripts.
- Size in `em` from root `font-size:clamp(12px,calc(100vw/48),3vh)`; fill the width,
  keep content compact, and never use `overflow:hidden`.
- HTML text is plain text; narration and explanations are Markdown outside it.
- If HTML is unavailable, describe the visual in one Markdown sentence.
