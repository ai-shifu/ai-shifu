/**
 * Visual boundary detection utilities for listen mode.
 *
 * Provides functions to detect and locate visual elements (HTML tags, markdown tables)
 * within text content for segmentation and rendering.
 */

import {
  type HtmlVisualKind,
  VISUAL_ELEMENT_PATTERNS,
  CLOSING_PATTERNS,
  MARKDOWN_TABLE,
} from './constants';
import { findFirstMarkdownTableBlock } from './markdown-table-parser';

/**
 * Visual element boundary with kind and position.
 */
export interface VisualBoundary {
  kind: HtmlVisualKind;
  start: number;
  end: number;
}

/**
 * Text visual block (HTML or markdown table).
 */
export type TextVisualBlock =
  | { kind: HtmlVisualKind; start: number; end: number }
  | { kind: 'markdown-table'; start: number; end: number };

/**
 * Find the first HTML visual element in text.
 * Searches for video, table, iframe, svg, and img tags.
 *
 * @param raw - The text to search
 * @returns Visual boundary object with kind, start, and end positions, or null if not found
 *
 * @example
 * findFirstHtmlVisualBlock("<p>Text</p><video src='...'/><p>More</p>")
 * // => { kind: 'video', start: 13, end: 32 }
 */
export const findFirstHtmlVisualBlock = (
  raw: string,
): VisualBoundary | null => {
  if (!raw) {
    return null;
  }

  const lower = raw.toLowerCase();
  const candidates: Array<{ kind: HtmlVisualKind; start: number }> = [];

  // Find all visual element start positions
  (
    Object.entries(VISUAL_ELEMENT_PATTERNS) as Array<[HtmlVisualKind, string]>
  ).forEach(([kind, pattern]) => {
    const start = lower.indexOf(pattern);
    if (start !== -1) {
      candidates.push({ kind, start });
    }
  });

  if (candidates.length === 0) {
    return null;
  }

  // Sort by start position and take the first
  candidates.sort((a, b) => a.start - b.start);
  const { kind, start } = candidates[0];

  // Look for closing tag
  const closePattern = CLOSING_PATTERNS[kind as keyof typeof CLOSING_PATTERNS];
  if (closePattern) {
    const closeIdx = lower.indexOf(closePattern, start);
    if (closeIdx !== -1) {
      const closeEnd = raw.indexOf('>', closeIdx);
      if (closeEnd !== -1) {
        return { kind, start, end: closeEnd + 1 };
      }
    }
  }

  // Best-effort support for self-closing <video ... /> / <iframe ... /> / <img ... /> tags.
  if (kind === 'video' || kind === 'iframe' || kind === 'img') {
    const openEnd = raw.indexOf('>', start);
    if (openEnd !== -1) {
      const head = raw.slice(start, openEnd + 1);
      if (MARKDOWN_TABLE.SELF_CLOSING_TAG_PATTERN.test(head)) {
        return { kind, start, end: openEnd + 1 };
      }
    }
  }

  return null;
};

/**
 * Find the first visual block (HTML or markdown table) in text.
 * Returns whichever appears first in the text.
 *
 * @param raw - The text to search
 * @returns Visual block object with kind, start, and end positions, or null if not found
 *
 * @example
 * findFirstTextVisualBlock("Text\n| A | B |\n| --- | --- |\nMore text")
 * // => { kind: 'markdown-table', start: 5, end: 27 }
 */
export const findFirstTextVisualBlock = (
  raw: string,
): TextVisualBlock | null => {
  const htmlBlock = findFirstHtmlVisualBlock(raw);
  const markdownTableBlock = findFirstMarkdownTableBlock(raw);

  if (!htmlBlock && !markdownTableBlock) {
    return null;
  }
  if (!htmlBlock) {
    return { kind: 'markdown-table', ...markdownTableBlock! };
  }
  if (!markdownTableBlock) {
    return htmlBlock;
  }

  return markdownTableBlock.start < htmlBlock.start
    ? { kind: 'markdown-table', ...markdownTableBlock }
    : htmlBlock;
};
