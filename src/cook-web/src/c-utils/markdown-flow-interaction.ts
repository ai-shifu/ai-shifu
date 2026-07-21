const ANONYMOUS_TEXT_INPUT_PATTERN =
  /^(\s*)\?\[(?!\s*%\{\{)\s*(?:(.*?)\s*(\|\||\|)\s*)?\.\.\.([^\]]*?)\](\s*)$/;

const escapeHtmlAttribute = (value: string) =>
  value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\r/g, '&#13;')
    .replace(/\n/g, '&#10;');

const escapeStringArrayAttribute = (values: string[]) =>
  escapeHtmlAttribute(JSON.stringify(values));

export const adaptMarkdownFlowInteractionForRender = (content: string) => {
  const match = ANONYMOUS_TEXT_INPUT_PATTERN.exec(content);
  const prompt = match?.[4]?.trim();
  if (!match || !prompt) {
    return content;
  }

  const options = match[2]
    ? match[2]
        .split(match[3])
        .map(option => option.trim())
        .filter(Boolean)
    : [];
  if (!options.length) {
    return `${match[1]}<custom-variable placeholder="${escapeHtmlAttribute(
      prompt,
    )}"></custom-variable>${match[5]}`;
  }

  const optionValues = escapeStringArrayAttribute(options);
  const multiSelectAttribute =
    match[3] === '||' ? ' data-is-multi-select="true"' : '';
  return `${match[1]}<custom-variable placeholder="${escapeHtmlAttribute(
    prompt,
  )}" data-button-texts="${optionValues}" data-button-values="${optionValues}"${multiSelectAttribute}></custom-variable>${match[5]}`;
};
