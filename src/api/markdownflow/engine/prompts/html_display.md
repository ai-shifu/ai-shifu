# Screens (HTML visuals)

Render every visual (slide, card, chart or diagram) as responsive HTML.

## Canvas and content

- One screen is one root `<div>` containing everything for that screen. The root is the canvas itself:
  place the main background, gradient or illustration on it. Inner cards may
  group content, but cannot be the only painted area in an empty full-height shell.
  White is valid; no color or visual style is required.
- Each screen, including later turns, needs its complete root, not an inner
  fragment. Respect the author's screen count. Each root is followed by its own
  narration; explaining an existing screen needs no new layout or repeated markup.
  A listening title or key-point visual is a complete low-density screen under
  the same canvas rules.
- Start with this root and retain its size rules:

```text
<div style="width:100%; min-height:100vh; overflow-x:hidden; overflow-y:auto; display:flex; flex-direction:column; align-items:center; padding:1em; font-size:clamp(12px,calc(100vw/48),3vh)">
  <!-- content -->
</div>
```

- Immediately after the opening root, put this required `<style>` and any needed
  `<script>`, before content and narration:

```text
<style>*,*::before,*::after{box-sizing:border-box;overflow-wrap:break-word;word-wrap:break-word}</style>
```

- Text in HTML is plain text; narration is Markdown outside it. Output raw HTML:
  no code fences, `<!DOCTYPE>`, `<html>`, `<head>`, `<body>`, elements outside the
  root or standalone styles/scripts. No external fonts, images or scripts.

## Responsive sizing

- The same HTML serves reading, listening and projection. Reading mode relaxes
  the root's full-viewport minimum and reserves the natural content height;
  listening and projection retain a full-stage canvas. Keep the minimum on the root only:
  no inner viewport/fixed heights or spacers recreating it.
- Keep root `min-height:100vh` so short screens do not expose the iframe background.
  Background and composition must both fill the canvas. Use flex/grid for header,
  main and optional footer; let main content grow into available space with local
  alignment while remaining naturally sized in reading mode. Do not pack the
  composition into a short top strip. Limit inner readable groups with `max-width`,
  not the painted canvas.
- Design for 16:9 by default and reflow for 4:3, square and portrait viewports.
  Do not lock the root to an aspect ratio. Keep all content visible; size
  everything in `em` from the root font, including spacing. No child `px`/`rem`
  font sizes or `vmin`/`vmax`.
- Type scale: cover title 3.5em/700, page title 2.5em/700, subtitle 2em/600,
  small heading 1.5em/600, key point 1.25em/500, body 1em, small 0.85em.
- Balance short covers and sparse screens with spacing and alignment, not extra
  facts/copy, excessive type, fixed padding, empty blocks or nested viewport
  minimums. Compact reading content must remain compact.
- Do not give the root a fixed `height:100vh` or `justify-content:center`.
  Never use `overflow:hidden` anywhere.

## Toolkit and graphics

Tailwind CSS v3, DaisyUI v4 and GSAP v3 are preloaded; prefer their components and
utilities to hand-written CSS.

- For steps, processes, phases, milestones, roadmaps and histories, always use
  DaisyUI `timeline`: `<ul class="timeline timeline-vertical">`, `<li>` containing
  `timeline-start`/`timeline-middle`/`timeline-end` and `timeline-box`, and `<hr />`
  between items, never before the first or after the last. Never use DaisyUI
  `steps`, which cannot hold icon + title + description.
- Timeline markers: emoji or fixed-size dot, e.g.
  `<span class="w-6 h-6 rounded-full bg-primary text-white flex items-center justify-center">1</span>`.
- GSAP may provide one short entrance animation; no `setTimeout` or animation
  the learner must wait for.
- Draw decorations (color blocks, glows, gradients, dividers) as backgrounds or
  absolute layers with `pointer-events:none`, `z-index:0`, non-negative offsets
  and width/height within the parent. They must take no layout space or protrude:
  overflow changes the measured content height.
- SVG is for pure graphics (icons, arrows, connectors), nested in HTML with a
  `viewBox` and percentage width. Limit its text to 4 words or 12 characters;
  prefer an emoji when available.
