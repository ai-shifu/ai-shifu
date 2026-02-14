/**
 * Markdown table parsing utilities for listen mode.
 *
 * Provides functions to detect, parse, and convert markdown tables
 * to HTML for rendering in sandbox environments.
 */

import { MARKDOWN_TABLE } from './constants';

/**
 * Table column alignment options.
 */
export type TableAlignment = 'left' | 'center' | 'right' | '';

/**
 * Escape HTML special characters in text.
 */
const escapeHtml = (raw: string): string =>
  raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

/**
 * Parse a markdown table row into cells.
 * Handles leading/trailing pipes and trims whitespace.
 *
 * @param line - The table row string (e.g., "| Cell 1 | Cell 2 |")
 * @returns Array of cell contents
 *
 * @example
 * parseMarkdownTableRow("| Name | Age |") // => ["Name", "Age"]
 * parseMarkdownTableRow("Name | Age") // => ["Name", "Age"]
 */
export const parseMarkdownTableRow = (line: string): string[] => {
  const trimmed = line.trim();
  const withoutLeading = trimmed.startsWith('|') ? trimmed.slice(1) : trimmed;
  const withoutEdges = withoutLeading.endsWith('|')
    ? withoutLeading.slice(0, -1)
    : withoutLeading;
  return withoutEdges.split('|').map(cell => cell.trim());
};

/**
 * Parse table alignment from separator line.
 * Detects left (:---), center (:---:), and right (---:) alignments.
 *
 * @param line - The separator line (e.g., "| :--- | :---: | ---: |")
 * @returns Array of alignment values for each column
 *
 * @example
 * parseMarkdownTableAlign("| :--- | :---: | ---: |")
 * // => ["left", "center", "right"]
 */
export const parseMarkdownTableAlign = (line: string): TableAlignment[] => {
  const cells = parseMarkdownTableRow(line);
  return cells.map(cell => {
    const token = cell.replace(/\s+/g, '');
    if (!MARKDOWN_TABLE.SEPARATOR_CELL_PATTERN.test(token)) {
      return '';
    }
    if (token.startsWith(':') && token.endsWith(':')) {
      return 'center';
    }
    if (token.endsWith(':')) {
      return 'right';
    }
    if (token.startsWith(':')) {
      return 'left';
    }
    return '';
  });
};

/**
 * Check if a line is a valid markdown table separator.
 * Separator must have at least 2 cells, each matching the pattern :?-{3,}:?
 *
 * @param line - The line to check
 * @returns True if the line is a valid separator
 *
 * @example
 * isMarkdownTableSeparatorLine("| --- | --- |") // => true
 * isMarkdownTableSeparatorLine("| :---: | ---: |") // => true
 * isMarkdownTableSeparatorLine("| --- |") // => false (only 1 cell)
 */
export const isMarkdownTableSeparatorLine = (line: string): boolean => {
  const cells = parseMarkdownTableRow(line);
  if (cells.length < MARKDOWN_TABLE.MIN_CELL_COUNT) {
    return false;
  }
  return cells.every(cell => {
    const token = cell.replace(/\s+/g, '');
    return MARKDOWN_TABLE.SEPARATOR_CELL_PATTERN.test(token);
  });
};

/**
 * Find the first markdown table block in text.
 * Returns the start and end positions of the table, or null if not found.
 *
 * A valid table must have:
 * 1. A header row with at least 2 cells containing pipes
 * 2. A separator row immediately after the header
 * 3. Optional body rows (stops at blank line or line without pipes)
 *
 * @param raw - The text to search
 * @returns Object with start/end positions, or null if no table found
 *
 * @example
 * findFirstMarkdownTableBlock("| A | B |\n| --- | --- |\n| 1 | 2 |")
 * // => { start: 0, end: 38 }
 */
export const findFirstMarkdownTableBlock = (
  raw: string,
): { start: number; end: number } | null => {
  if (!raw) {
    return null;
  }

  const lines = raw.split('\n');
  if (lines.length < 2) {
    return null;
  }

  const lineStarts: number[] = [];
  let cursor = 0;
  lines.forEach(line => {
    lineStarts.push(cursor);
    cursor += line.length + 1;
  });

  for (let index = 0; index < lines.length - 1; index += 1) {
    const headerLine = lines[index];
    const separatorLine = lines[index + 1];
    if (!headerLine.includes('|') || !separatorLine.includes('|')) {
      continue;
    }
    const headerCells = parseMarkdownTableRow(headerLine);
    if (headerCells.length < MARKDOWN_TABLE.MIN_CELL_COUNT) {
      continue;
    }
    if (!isMarkdownTableSeparatorLine(separatorLine)) {
      continue;
    }

    let endLine = index + 2;
    while (endLine < lines.length) {
      const line = lines[endLine];
      if (!line.trim()) {
        break;
      }
      if (!line.includes('|')) {
        break;
      }
      endLine += 1;
    }

    const start = lineStarts[index];
    const lastLineIndex = Math.max(endLine - 1, index + 1);
    let end = lineStarts[lastLineIndex] + lines[lastLineIndex].length;
    if (end < raw.length && raw[end] === '\n') {
      end += 1;
    }
    return { start, end };
  }

  return null;
};

/**
 * Convert a markdown table to HTML for sandbox rendering.
 * Preserves column alignments and escapes HTML in cell contents.
 *
 * @param raw - The markdown table text
 * @returns HTML string wrapped in <div><table>...</table></div>, or null if invalid
 *
 * @example
 * markdownTableToSandboxHtml("| Name | Age |\n| :--- | ---: |\n| Alice | 25 |")
 * // => "<div><table><thead>...</thead><tbody>...</tbody></table></div>"
 */
export const markdownTableToSandboxHtml = (raw: string): string | null => {
  const lines = (raw || '')
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean);
  if (lines.length < 2) {
    return null;
  }

  const headerLine = lines[0];
  const separatorLine = lines[1];
  if (!headerLine.includes('|') || !separatorLine.includes('|')) {
    return null;
  }

  const headers = parseMarkdownTableRow(headerLine);
  const alignments = parseMarkdownTableAlign(separatorLine);
  if (!headers.length || !alignments.length) {
    return null;
  }

  const bodyLines = lines.slice(2).filter(line => line.includes('|'));
  const headerHtml = headers
    .map((header, index) => {
      const align = alignments[index] || '';
      const alignAttr = align ? ` style="text-align:${align};"` : '';
      return `<th${alignAttr}>${escapeHtml(header)}</th>`;
    })
    .join('');

  const bodyHtml = bodyLines
    .map(line => {
      const cells = parseMarkdownTableRow(line);
      if (!cells.length) {
        return '';
      }
      const cellsHtml = cells
        .map((cell, index) => {
          const align = alignments[index] || '';
          const alignAttr = align ? ` style="text-align:${align};"` : '';
          return `<td${alignAttr}>${escapeHtml(cell)}</td>`;
        })
        .join('');
      return `<tr>${cellsHtml}</tr>`;
    })
    .filter(Boolean)
    .join('');

  return `<div><table><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table></div>`;
};
