import {
  splitContentSegments,
  type RenderSegment,
} from 'markdown-flow-ui/renderer';
import {
  type HtmlSandboxRootTag,
  FIXED_MARKER_PATTERN,
  SANDBOX_ROOT_TAGS,
} from './constants';
import { markdownTableToSandboxHtml } from './markdown-table-parser';
import { findFirstTextVisualBlock } from './visual-boundary-detector';

const isFixedMarkerText = (raw: string) => {
  const trimmed = (raw || '').trim();
  return Boolean(trimmed && FIXED_MARKER_PATTERN.test(trimmed));
};

export const isListenModeSpeakableText = (raw: string) => {
  const trimmed = (raw || '').trim();
  if (trimmed.length < 2) {
    return false;
  }
  // Avoid synthesizing MarkdownFlow fixed marker delimiters such as `===`/`!===`.
  if (isFixedMarkerText(trimmed)) {
    return false;
  }
  return true;
};

const splitTextByVisualBlocks = (raw: string): RenderSegment[] => {
  if (!raw || !raw.trim()) {
    return [];
  }

  const block = findFirstTextVisualBlock(raw);
  if (!block) {
    return [{ type: 'text', value: raw }];
  }

  const before = raw.slice(0, block.start);
  const matched = raw.slice(block.start, block.end);
  const after = raw.slice(block.end);

  const output: RenderSegment[] = [];
  if (before.trim()) {
    output.push({ type: 'text', value: before });
  }
  if (block.kind === 'markdown-table') {
    const markdownTableSandbox = markdownTableToSandboxHtml(matched);
    if (markdownTableSandbox) {
      output.push({
        type: 'sandbox',
        value: markdownTableSandbox,
      });
    } else {
      output.push({
        type: 'markdown',
        value: matched,
      });
    }
  } else {
    if (block.kind === 'iframe') {
      output.push({
        type: 'sandbox',
        value: matched,
      });
    } else if (block.kind === 'table') {
      // In blackboard mode, IframeSandbox only mounts content extracted from
      // sandbox-root HTML blocks. Wrap bare <table> so it renders in sandbox.
      output.push({
        type: 'sandbox',
        value: `<div>${matched}</div>`,
      });
    } else {
      output.push({
        type: 'markdown',
        value: matched,
      });
    }
  }
  if (after.trim()) {
    output.push(...splitTextByVisualBlocks(after));
  }
  return output;
};

const splitSandboxByRootBoundary = (
  raw: string,
): { head: string; rest: string } | null => {
  if (!raw || !raw.trim()) {
    return null;
  }

  const trimmed = raw.trimStart();
  const lower = trimmed.toLowerCase();
  const match = lower.match(/^<([a-z0-9-]+)/);
  if (!match) {
    return null;
  }

  const tag = match[1] as HtmlSandboxRootTag;
  if (!SANDBOX_ROOT_TAGS.includes(tag)) {
    return null;
  }

  const closeTag = `</${tag}>`;
  const closeIdx =
    tag === 'iframe' ? lower.indexOf(closeTag) : lower.lastIndexOf(closeTag);
  if (closeIdx === -1) {
    return null;
  }

  let end = closeIdx + closeTag.length;
  // Keep trailing fixed markers on the same line (e.g. `</div> ===`).
  const nl = trimmed.indexOf('\n', end);
  const lineEnd = nl === -1 ? trimmed.length : nl;
  const tail = trimmed.slice(end, lineEnd);
  if (/^[\s!=]*$/.test(tail)) {
    end = nl === -1 ? trimmed.length : nl + 1;
  }

  if (end <= 0 || end >= trimmed.length) {
    return null;
  }

  const rest = trimmed.slice(end);
  if (!rest.trim()) {
    return null;
  }

  return { head: trimmed.slice(0, end), rest };
};

const splitSandboxTableBoundary = (
  raw: string,
): { table: string; rest: string } | null => {
  if (!raw || !raw.trim()) {
    return null;
  }

  const trimmed = raw.trimStart();
  if (!/^\s*<table\b/i.test(trimmed)) {
    return null;
  }

  const lower = trimmed.toLowerCase();
  const closeTag = '</table>';
  const closeIdx = lower.indexOf(closeTag);
  if (closeIdx === -1) {
    return null;
  }

  let end = closeIdx + closeTag.length;
  const nl = trimmed.indexOf('\n', end);
  const lineEnd = nl === -1 ? trimmed.length : nl;
  const tail = trimmed.slice(end, lineEnd);
  if (/^[\s!=]*$/.test(tail)) {
    end = nl === -1 ? trimmed.length : nl + 1;
  }

  const table = trimmed.slice(0, end);
  const rest = trimmed.slice(end);
  return { table, rest };
};

const mergeHtmlTableSegments = (segments: RenderSegment[]): RenderSegment[] => {
  if (!segments.length) {
    return segments;
  }

  const output: RenderSegment[] = [];

  for (let index = 0; index < segments.length; index += 1) {
    const segment = segments[index];
    const raw = typeof segment.value === 'string' ? segment.value : '';
    if (!raw) {
      output.push(segment);
      continue;
    }
    const lower = raw.toLowerCase();
    const tableStart = lower.indexOf('<table');
    if (tableStart === -1) {
      output.push(segment);
      continue;
    }

    // If the closing tag is already present, keep the segment intact.
    // `splitTextByVisualBlocks()` will handle turning it into a visual sandbox segment.
    if (lower.indexOf('</table', tableStart) !== -1) {
      output.push(segment);
      continue;
    }

    // Merge forward to reconstruct tables that were split by other HTML/markdown
    // detectors (e.g. <img> inside <table>), otherwise the table ends up as
    // non-visual `text` and gets dropped from slides.
    let merged = raw;
    let mergedLower = lower;
    let foundClose = false;
    let nextIndex = index;

    for (let scan = index + 1; scan < segments.length; scan += 1) {
      const next = segments[scan];
      const nextValue = typeof next.value === 'string' ? next.value : '';
      const nextLower = nextValue.toLowerCase();
      merged += nextValue;
      mergedLower += nextLower;
      if (mergedLower.includes('</table')) {
        foundClose = true;
        nextIndex = scan;
        break;
      }
    }

    if (!foundClose) {
      output.push(segment);
      continue;
    }

    output.push({ ...segment, value: merged });
    index = nextIndex;
  }

  return output;
};

export const splitListenModeSegments = (raw: string): RenderSegment[] => {
  const baseSegments = mergeHtmlTableSegments(
    splitContentSegments(raw || '', true),
  );
  if (!baseSegments.length) {
    return baseSegments;
  }

  const output: RenderSegment[] = [];
  baseSegments.forEach((segment, index) => {
    if (segment.type !== 'text') {
      if (segment.type === 'sandbox') {
        const sandboxRaw =
          typeof segment.value === 'string' ? segment.value : '';
        const splitTable = splitSandboxTableBoundary(sandboxRaw);
        if (splitTable) {
          output.push({
            type: 'sandbox',
            value: `<div>${splitTable.table}</div>`,
          });
          if (splitTable.rest.trim()) {
            output.push(...splitListenModeSegments(splitTable.rest));
          }
          return;
        }

        const split = splitSandboxByRootBoundary(segment.value || '');
        if (split) {
          output.push({ type: 'sandbox', value: split.head });
          output.push(...splitListenModeSegments(split.rest));
          return;
        }
      }
      if (segment.type === 'markdown') {
        const markdownRaw =
          typeof segment.value === 'string' ? segment.value : '';
        const markdownTableSandbox = markdownTableToSandboxHtml(markdownRaw);
        if (markdownTableSandbox) {
          output.push({
            type: 'sandbox',
            value: markdownTableSandbox,
          });
          return;
        }

        // splitContentSegments() may return an entire markdown block as a
        // single segment. If that block contains an embedded visual boundary
        // (markdown table, iframe, html table/video, etc.), split it so the
        // visual can get its own listen slide.
        if (!/^\s*```/.test(markdownRaw) && !/^\s*~~~/.test(markdownRaw)) {
          const splitSegments = splitTextByVisualBlocks(markdownRaw);
          const hasSplitVisual = splitSegments.some(
            candidate => candidate.type !== 'text',
          );
          if (hasSplitVisual) {
            output.push(...splitSegments);
            return;
          }
        }
      }
      output.push(segment);
      return;
    }

    // Drop fixed marker-only segments that would otherwise become speakable.
    const next = baseSegments[index + 1];
    if (
      isFixedMarkerText(segment.value) &&
      next &&
      (next.type === 'sandbox' || next.type === 'markdown')
    ) {
      return;
    }

    output.push(...splitTextByVisualBlocks(segment.value));
  });

  return output;
};
