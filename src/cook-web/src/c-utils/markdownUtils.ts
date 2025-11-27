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

const MERMAID_FENCE = '```mermaid';
const STREAMING_MARKER_REGEX = /```mermaid\s*_streaming\s*/gi;

const stripStreamingMarker = (text: string) =>
  text.replace(STREAMING_MARKER_REGEX, `${MERMAID_FENCE}\n`);

const getMermaidPlaceholderContent = () => {
  const generatingKey = 'module.chat.generating';
  const thinkingKey = 'module.chat.thinking';
  const translated = i18n.t(generatingKey);
  const fallback = i18n.t(thinkingKey);
  let message = 'Loading...';
  if (
    typeof translated === 'string' &&
    translated.trim().length &&
    translated !== generatingKey
  ) {
    message = translated;
  } else if (
    typeof fallback === 'string' &&
    fallback.trim().length &&
    fallback !== thinkingKey
  ) {
    message = fallback;
  }
  return `graph TD\n${message}`;
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
