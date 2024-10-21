
export const fixMarkdown = (text) => {
  return fixCode(text);
}

/**
 * 修改 markdown 中代码段 ``` 后回车不正常的问题
 */
export const fixCode = (text) => {
  return text.replace(/``` /g, '```\n')
}

export const fixMarkdownStream = (text, curr) => {
  return fixCodeStream(text, curr);
}
export const fixCodeStream = (text, curr) => {
  if (text.endsWith('```') && curr === ' ') {
    return '\n';
  }

  return curr;
}
