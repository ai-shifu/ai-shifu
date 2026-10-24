# Screens (HTML visuals)

Whenever you output a visual (a slide, a card, a chart, a diagram), write it as HTML that follows these rules. They come from what worked in MarkdownFlow 1.0: a screen must fill the stage, scale with it, and look designed rather than pasted.

## Screen contract

- One screen = one root `<div>`; everything for that screen is inside it. The root is the canvas itself: put the screen's main background, gradient or background illustration on it. Inner cards may group information, but must not be the only painted area inside an otherwise empty full-height shell. An intentionally white canvas is fine; do not impose a color or visual style. Several screens in one turn are fine: each root `<div>` is its own screen, followed by its own narration.
- Every screen, including one in a later turn, must repeat its complete canvas root; an inner layout fragment is not a new screen. Respect the author's requested screen count. Narrating an existing screen does not require another screen, an alternative layout or repeated markup.
- In listening lessons, a concise title or key-point visual is still a complete low-density screen using this full-canvas contract. Do not make a short content-height card inside a blank full-height shell.
- The root fills the stage and scales its type with it. Start from this container and keep its size rules:

```text
<div style="width:100%; min-height:100vh; overflow-x:hidden; overflow-y:auto; display:flex; flex-direction:column; align-items:center; padding:1em; font-size:clamp(12px,calc(100vw/48),3vh)">
  <!-- content -->
</div>
```

- Put a `<style>` (and, if needed, a `<script>`) block right after the root `<div>`, never after narration text. Always include:

```text
<style>*,*::before,*::after{box-sizing:border-box;overflow-wrap:break-word;word-wrap:break-word}</style>
```

- The same HTML is used in reading, listening and projection. Reading mode relaxes the root's full-viewport minimum and reserves the natural content height; listening and projection keep a full-stage canvas. Keep the minimum on the root only: do not recreate it on inner content with viewport heights, fixed heights or spacer elements.
- Design for a 16:9 landscape stage by default, then adapt to the actual viewport's width and height, including 4:3, square and portrait stages. Do not lock the root to an aspect ratio. Reflow columns and scale spacing with the existing em sizing so all content remains visible.
- Text inside HTML is plain text, no Markdown. Narration is Markdown text outside the screen.

## Sizing

- Size everything in `em` so the whole screen scales from the root `font-size`. Never set `px`/`rem` font sizes on children; never use `vmin`/`vmax`.
- Type scale: cover title 3.5em/700, page title 2.5em/700, subtitle 2em/600, small heading 1.5em/600, key point 1.25em/500, body 1em, small 0.85em.
- Keep `min-height:100vh` on the root: without a full-stage minimum, short content can expose the iframe's white background below the screen. This minimum sizes only the root; it does not make an inner cover card fill the canvas. The main background and composition must follow the canvas together.
- Use flex or grid to arrange the header, main content and optional footer. Let the main content region grow into available space, with local alignment inside it, while remaining naturally sized when the reading host relaxes the root minimum. Do not pack the entire composition into a short strip at the top. Use `max-width` for readable inner content groups, not to bound the entire painted canvas.
- For short covers and low-density screens, balance the authored content with deliberate spacing and alignment. Do not add facts or extra copy, enlarge text excessively, or add fixed padding, empty blocks or nested viewport minimums merely to fill the stage. Compact reading content must remain compact.
- Do not give the root a fixed `height:100vh`, and do not `justify-content:center` the root: both leave dead space around short content. Never use `overflow:hidden` anywhere.

## Toolkit

The stage preloads Tailwind CSS v3, DaisyUI v4 and GSAP v3. Prefer DaisyUI components and Tailwind utilities over hand-written CSS.

- Steps, processes, phases, milestones, roadmaps, histories: always DaisyUI `timeline` (`<ul class="timeline timeline-vertical">`, `<li>` with `timeline-start`/`timeline-middle`/`timeline-end` and `timeline-box`, `<hr />` between items, omitted before the first and after the last). Never DaisyUI `steps`: it cannot hold icon + title + description.
- Node markers in `timeline-middle`: an emoji or a fixed-size dot such as `<span class="w-6 h-6 rounded-full bg-primary text-white flex items-center justify-center">1</span>`.
- GSAP is available for a single, short entrance animation; never `setTimeout`, never animation that the learner must wait for.

## Decoration and graphics

- Decoration (color blocks, glows, gradients, dividers) is drawn with the container's `background`, or as an absolutely positioned layer with `pointer-events:none`, `z-index:0`, non-negative offsets, and width/height within the parent. Decoration must never take layout space or protrude outside the container: the stage measures the content height, and overflow stretches it.
- SVG only for pure graphics (icons, arrows, connectors), nested in HTML, with a `viewBox` and percentage width; at most 4 words or 12 characters of text inside an SVG. Prefer an emoji when one exists.

## Never

- No code fences around HTML, no `<!DOCTYPE>`, `<html>`, `<head>` or `<body>`; no elements outside the root `<div>`.
- No `<style>`/`<script>` without a screen before them.
- No external assets (fonts, images, scripts from the network).
