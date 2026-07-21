const ANONYMOUS_TEXT_INPUT_PATTERN =
  /^(\s*)\?\[(?!\s*%\{\{)\s*(?:(.*?)\s*(\|\||\|)\s*)?\.\.\.([^\]]*?)\](\s*)$/;
const SINGLE_OPTION_SEPARATOR_PATTERN = /(?<!\|)\|(?!\|)/;
const BUTTON_VALUE_PATTERN = /^(.+?)\/\/(.+)$/;

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

  const optionContent = match[2]?.trim();
  const separatorProbe = optionContent ? `${optionContent}${match[3]}` : '';
  const firstSeparatorIndex = separatorProbe.indexOf('|');
  const firstMultiSeparatorIndex = separatorProbe.indexOf('||');
  const isMultiSelect =
    firstMultiSeparatorIndex !== -1 &&
    firstMultiSeparatorIndex <= firstSeparatorIndex;
  const optionSeparator = isMultiSelect
    ? '||'
    : SINGLE_OPTION_SEPARATOR_PATTERN;
  const options = optionContent
    ? optionContent
        .split(optionSeparator)
        .map(option => option.trim())
        .filter(Boolean)
    : [];
  if (!options.length) {
    return `${match[1]}<custom-variable placeholder="${escapeHtmlAttribute(
      prompt,
    )}"></custom-variable>${match[5]}`;
  }

  const parsedOptions = options.map(option => {
    const valueMatch = BUTTON_VALUE_PATTERN.exec(option);
    return {
      text: valueMatch?.[1]?.trim() || option,
      value: valueMatch?.[2]?.trim() || option,
    };
  });
  const optionTexts = escapeStringArrayAttribute(
    parsedOptions.map(option => option.text),
  );
  const optionValues = escapeStringArrayAttribute(
    parsedOptions.map(option => option.value),
  );
  const multiSelectAttribute = isMultiSelect
    ? ' data-is-multi-select="true"'
    : '';
  return `${match[1]}<custom-variable placeholder="${escapeHtmlAttribute(
    prompt,
  )}" data-button-texts="${optionTexts}" data-button-values="${optionValues}"${multiSelectAttribute}></custom-variable>${match[5]}`;
};
