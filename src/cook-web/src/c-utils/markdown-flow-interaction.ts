const ANONYMOUS_TEXT_INPUT_PATTERN =
  /^(\s*)\?\[(?!\s*%\{\{)\s*(?:(.*?)(\|\||\|)\s*)?\.\.\.([^\]]*?)\](\s*)$/;
const ANONYMOUS_INTERACTION_PATTERN =
  /^(\s*)\?\[(?!\s*%\{\{)\s*([^\]]*?)\s*\](\s*)$/;
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

const parseAnonymousOptions = (optionContent: string) => {
  const firstSeparatorIndex = optionContent.indexOf('|');
  const firstMultiSeparatorIndex = optionContent.indexOf('||');
  const isMultiSelect =
    firstMultiSeparatorIndex !== -1 &&
    firstMultiSeparatorIndex === firstSeparatorIndex;
  const optionSeparator = isMultiSelect
    ? '||'
    : SINGLE_OPTION_SEPARATOR_PATTERN;
  const options = optionContent
    ? optionContent
        .split(optionSeparator)
        .map(option => option.trim())
        .filter(Boolean)
    : [];
  const parsedOptions = options.map(option => {
    const valueMatch = BUTTON_VALUE_PATTERN.exec(option);
    return {
      text: valueMatch?.[1]?.trim() || option,
      value: valueMatch?.[2]?.trim() || option,
    };
  });

  return { isMultiSelect, parsedOptions };
};

const renderAnonymousInteraction = ({
  leadingWhitespace,
  trailingWhitespace,
  prompt,
  isMultiSelect,
  parsedOptions,
}: {
  leadingWhitespace: string;
  trailingWhitespace: string;
  prompt?: string;
  isMultiSelect: boolean;
  parsedOptions: Array<{ text: string; value: string }>;
}) => {
  const attributes: string[] = [];

  if (prompt) {
    attributes.push(`placeholder="${escapeHtmlAttribute(prompt)}"`);
  }
  if (parsedOptions.length) {
    attributes.push(
      `data-button-texts="${escapeStringArrayAttribute(
        parsedOptions.map(option => option.text),
      )}"`,
      `data-button-values="${escapeStringArrayAttribute(
        parsedOptions.map(option => option.value),
      )}"`,
    );
  }
  if (isMultiSelect) {
    attributes.push('data-is-multi-select="true"');
  }

  return `${leadingWhitespace}<custom-variable${
    attributes.length ? ` ${attributes.join(' ')}` : ''
  }></custom-variable>${trailingWhitespace}`;
};

export const adaptMarkdownFlowInteractionForRender = (content: string) => {
  const textInputMatch = ANONYMOUS_TEXT_INPUT_PATTERN.exec(content);
  if (textInputMatch) {
    const prompt = textInputMatch[4]?.trim();
    if (!prompt) {
      return content;
    }

    const optionContent = textInputMatch[2]
      ? `${textInputMatch[2]}${textInputMatch[3]}`.trim()
      : '';
    const { isMultiSelect, parsedOptions } =
      parseAnonymousOptions(optionContent);
    return renderAnonymousInteraction({
      leadingWhitespace: textInputMatch[1],
      trailingWhitespace: textInputMatch[5],
      prompt,
      isMultiSelect,
      parsedOptions,
    });
  }

  const interactionMatch = ANONYMOUS_INTERACTION_PATTERN.exec(content);
  if (!interactionMatch) {
    return content;
  }

  const optionContent = interactionMatch[2].trim();
  const { isMultiSelect, parsedOptions } = parseAnonymousOptions(optionContent);
  if (!isMultiSelect || !parsedOptions.length) {
    return content;
  }

  return renderAnonymousInteraction({
    leadingWhitespace: interactionMatch[1],
    trailingWhitespace: interactionMatch[3],
    isMultiSelect,
    parsedOptions,
  });
};
