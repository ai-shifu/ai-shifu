export const fixMarkdown = (text) => {
  return fixCode(text);
};

/**
 * fix markdown code block ``` key after enter not normal
 */
export const fixCode = (text) => {
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
