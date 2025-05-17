
export const fixMarkdown = (text: string): string => {
  return fixCode(text);
};

/**
 * fix markdown code block ``` key after enter not normal
 */
export const fixCode = (text: string): string => {
  return text.replace(/``` /g, '```\n');
};

export const fixMarkdownStream = (text: string, curr: string): string => {
  return fixCodeStream(text, curr);
};
export const fixCodeStream = (text: string, curr: string): string => {
  if (text.endsWith('```') && curr === ' ') {
    return '\n';
  }

  return curr;
};
