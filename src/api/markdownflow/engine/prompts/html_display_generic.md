# Screens (HTML visuals) for a plain renderer

The host renders your HTML without preloaded libraries. When a visual helps, keep it simple and self-contained:

- One screen = one root `<div>` with inline styles only; no external assets, no frameworks, no `<script>`.
- Size in `em` from a root `font-size:clamp(12px,calc(100vw/48),3vh)`; fill the width, keep content compact; never `overflow:hidden`.
- Text inside HTML is plain text; narration and explanations are Markdown outside the screen.
- If the host cannot show HTML at all, describe the visual in one Markdown sentence instead of skipping the point.
