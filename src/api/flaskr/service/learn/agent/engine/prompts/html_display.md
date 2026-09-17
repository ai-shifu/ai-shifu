# Screens (HTML visuals)

Whenever you output a visual (a slide, a card, a chart, a diagram), write it as HTML that follows these rules. They come from what worked in MarkdownFlow 1.0: a screen must fill the stage, scale with it, and look designed rather than pasted.

## Screen contract

- One screen = one root `<div>`; everything for that screen is inside it. Several screens in one turn are fine: each root `<div>` is its own screen, followed by its own narration.
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

- Screens default to a 16:9 landscape layout; keep content vertically compact so it fits without scrolling. Use responsive prefixes (`sm:` `md:` `lg:`) when a portrait or square stage is likely.
- Text inside HTML is plain text, no Markdown. Narration is Markdown text outside the screen.

## Sizing

- Size everything in `em` so the whole screen scales from the root `font-size`. Never set `px`/`rem` font sizes on children; never use `vmin`/`vmax`.
- Type scale: cover title 3.5em/700, page title 2.5em/700, subtitle 2em/600, small heading 1.5em/600, key point 1.25em/500, body 1em, small 0.85em.
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
