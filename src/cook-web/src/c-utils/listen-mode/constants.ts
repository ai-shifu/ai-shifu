/**
 * Shared constants for listen mode visual element detection.
 * These patterns are mirrored in the backend (src/api/flaskr/service/tts/pipeline.py)
 * to ensure consistent boundary detection across frontend and backend.
 */

/**
 * HTML visual element kinds that can be detected in content.
 */
export type HtmlVisualKind = 'video' | 'table' | 'iframe' | 'svg' | 'img';

/**
 * Valid root tags for sandbox HTML containers.
 */
export type HtmlSandboxRootTag =
  | 'iframe'
  | 'div'
  | 'section'
  | 'article'
  | 'main'
  | 'template';

/**
 * HTML opening tag patterns for visual elements.
 * Keys map to HtmlVisualKind, values are the lowercase tag strings to search for.
 */
export const VISUAL_ELEMENT_PATTERNS = {
  video: '<video',
  table: '<table',
  iframe: '<iframe',
  svg: '<svg',
  img: '<img',
} as const;

/**
 * Closing tag patterns for visual elements.
 * Used to find the end boundary of detected visual blocks.
 */
export const CLOSING_PATTERNS = {
  video: '</video',
  table: '</table',
  iframe: '</iframe',
  svg: '</svg',
} as const;

/**
 * Markdown table detection constants.
 */
export const MARKDOWN_TABLE = {
  /**
   * Regex to validate table separator cells (e.g., :---, :---:, ---:).
   * Must have at least 3 dashes, optionally prefixed/suffixed with colons.
   */
  SEPARATOR_CELL_PATTERN: /^:?-{3,}:?$/,

  /**
   * Regex to detect self-closing tags (e.g., <video />, <iframe />).
   */
  SELF_CLOSING_TAG_PATTERN: /\/\s*>$/,

  /**
   * Minimum number of cells required for a valid table row.
   */
  MIN_CELL_COUNT: 2,

  /**
   * Alignment tokens for table columns.
   */
  ALIGNMENTS: {
    LEFT: 'left',
    CENTER: 'center',
    RIGHT: 'right',
    NONE: '',
  } as const,
} as const;

/**
 * Valid sandbox root tags for HTML wrapping.
 * Elements not in this list need to be wrapped in a container.
 */
export const SANDBOX_ROOT_TAGS: readonly HtmlSandboxRootTag[] = [
  'iframe',
  'div',
  'section',
  'article',
  'main',
  'template',
] as const;

/**
 * Fixed marker pattern for MarkdownFlow delimiters (e.g., ===, !===).
 */
export const FIXED_MARKER_PATTERN = /^!?=+$/;
