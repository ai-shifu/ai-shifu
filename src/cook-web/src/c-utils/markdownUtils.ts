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

const findIncompleteMarkdownImageStart = (text: string): number => {
  const imageStart = text.lastIndexOf('![');
  if (imageStart === -1) {
    return -1;
  }

  const imageOpen = text.indexOf('](', imageStart + 2);
  if (imageOpen === -1) {
    return imageStart;
  }

  let depth = 1;
  for (let i = imageOpen + 2; i < text.length; i += 1) {
    const char = text[i];
    if (char === '\\') {
      i += 1;
      continue;
    }
    if (char === '(') {
      depth += 1;
      continue;
    }
    if (char === ')') {
      depth -= 1;
      if (depth === 0) {
        return -1;
      }
    }
  }

  return imageStart;
};

const findIncompleteHtmlImageStart = (text: string): number => {
  const lowerText = text.toLowerCase();
  const imageStart = lowerText.lastIndexOf('<img');
  if (imageStart === -1) {
    return -1;
  }

  let quote: '"' | "'" | null = null;
  for (let i = imageStart + 4; i < text.length; i += 1) {
    const char = text[i];
    if (char === '\\') {
      i += 1;
      continue;
    }
    if (quote) {
      if (char === quote) {
        quote = null;
      }
      continue;
    }
    if (char === '"' || char === "'") {
      quote = char;
      continue;
    }
    if (char === '>') {
      return -1;
    }
  }

  return imageStart;
};

export const maskIncompleteImageToken = (text: string): string => {
  if (!text) {
    return text;
  }

  const markdownImageStart = findIncompleteMarkdownImageStart(text);
  const htmlImageStart = findIncompleteHtmlImageStart(text);
  const cutoff = [markdownImageStart, htmlImageStart]
    .filter(index => index >= 0)
    .sort((a, b) => a - b)[0];

  if (typeof cutoff !== 'number') {
    return text;
  }

  return text.slice(0, cutoff);
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

export const maskIncompleteVisualTokens = (text: string): string => {
  const mermaidSafeText = maskIncompleteMermaidBlock(text);
  return maskIncompleteImageToken(mermaidSafeText);
};
