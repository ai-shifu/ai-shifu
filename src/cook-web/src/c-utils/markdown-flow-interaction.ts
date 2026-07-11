const ANONYMOUS_TEXT_INPUT_PATTERN = /^(\s*)\?\[\s*\.\.\.([^\]]*?)\](\s*)$/;

const escapeHtmlAttribute = (value: string) =>
  value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\r/g, '&#13;')
    .replace(/\n/g, '&#10;');

export const adaptMarkdownFlowInteractionForRender = (content: string) => {
  const match = ANONYMOUS_TEXT_INPUT_PATTERN.exec(content);
  const prompt = match?.[2];
  if (!match || !prompt?.trim()) {
    return content;
  }

  return `${match[1]}<custom-variable placeholder="${escapeHtmlAttribute(
    prompt.trim(),
  )}"></custom-variable>${match[3]}`;
};
