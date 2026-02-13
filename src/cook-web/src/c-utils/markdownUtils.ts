import i18n from '@/i18n';

export const fixMarkdown = text => {
  return fixCode(text);
};

/**
 * fix markdown code block ``` key after enter not normal
 */
export const fixCode = text => {
  return text.replace(/``` /g, '```\n');
};

export const fixMarkdownStream = (text, curr) => {
  return fixCodeStream(text, curr);
};
export const fixCodeStream = (text, curr) => {
  if (text.endsWith('```') && curr === ' ') {
    return '\n';
  }

  return curr;
};

const VISUAL_CODE_FENCE_REGEX =
  /(^|\n)(`{3,}|~{3,})[ \t]*([a-zA-Z0-9_+-]*)[^\r\n]*\r?\n([\s\S]*?)\r?\n\2[ \t]*(?=\s*(?:\r?\n|$))/g;

const VISUAL_LANGS = new Set(['', 'svg', 'svg+xml', 'html', 'xml', 'xhtml']);
const VISUAL_ROOT_TAG_REGEX =
  /^<(svg|iframe|video|table|div|section|article|main|html)\b/i;

const normalizeEscapedVisualFenceBody = (body: string): string => {
  if (!body || body.indexOf('\\') === -1) {
    return body;
  }

  return body
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\r/g, '\r')
    .replace(/\\t/g, '\t')
    .replace(/\\"/g, '"')
    .replace(/\\'/g, "'");
};

const stripDocumentPreamble = (body: string): string => {
  if (!body) {
    return body;
  }
  return body
    .replace(/^<\?xml[^>]*>\s*/i, '')
    .replace(/^<!doctype[^>]*>\s*/i, '');
};

const shouldUnwrapVisualFence = (lang: string, body: string): boolean => {
  const normalizedLang = (lang || '').trim().toLowerCase();
  if (!VISUAL_LANGS.has(normalizedLang)) {
    return false;
  }

  const normalizedBody = normalizeEscapedVisualFenceBody(body || '');
  const trimmedBody = normalizedBody.trim();
  if (!trimmedBody) {
    return false;
  }

  if (normalizedLang === 'svg' || normalizedLang === 'svg+xml') {
    return true;
  }

  const bodyWithoutPreamble = stripDocumentPreamble(trimmedBody);
  return VISUAL_ROOT_TAG_REGEX.test(bodyWithoutPreamble);
};

/**
 * Unwrap fenced blocks that actually contain renderable visual markup.
 * This prevents LLM outputs like ```svg ... ``` from being shown as raw code.
 */
export const unwrapVisualCodeFence = (text: string): string => {
  if (!text || (text.indexOf('```') === -1 && text.indexOf('~~~') === -1)) {
    return text;
  }

  return text.replace(
    VISUAL_CODE_FENCE_REGEX,
    (fullMatch, lineBreak, _fence, lang, body) => {
      if (!shouldUnwrapVisualFence(lang, body)) {
        return fullMatch;
      }
      const normalizedBody = normalizeEscapedVisualFenceBody(body || '');
      return `${lineBreak}${normalizedBody}`;
    },
  );
};

const MERMAID_FENCE = '```mermaid';
const STREAMING_MARKER_REGEX = /```mermaid\s*_streaming\s*/gi;

const stripStreamingMarker = (text: string) =>
  text.replace(STREAMING_MARKER_REGEX, `${MERMAID_FENCE}\n`);

const getMermaidPlaceholderContent = () => {
  const translated = i18n.t('module.chat.generating');
  return `graph TD
    placeholder["${translated}"]
    classDef ghost stroke-dasharray:4 3;
    class placeholder ghost;`;
};

/**
 * Prevent mermaid from rendering while the fenced block is still streaming.
 * During SSE we may temporarily have invalid diagrams (e.g. missing closing `]` or ```),
 * which causes mermaid to throw parsing errors that flash in the UI.
 * We temporarily rename the language to `mermaid-streaming` until the fence closes.
 */
export const maskIncompleteMermaidBlock = (text: string): string => {
  if (!text || text.indexOf('```') === -1) {
    return text;
  }

  const lowerText = text.toLowerCase();
  const fenceIdx = lowerText.lastIndexOf(MERMAID_FENCE);
  if (fenceIdx === -1) {
    return text;
  }

  const closingIdx = lowerText.indexOf('```', fenceIdx + MERMAID_FENCE.length);
  if (closingIdx === -1) {
    return (
      text.slice(0, fenceIdx) +
      `${MERMAID_FENCE}\n${getMermaidPlaceholderContent()}\n\`\`\``
    );
  }

  return stripStreamingMarker(text);
};
