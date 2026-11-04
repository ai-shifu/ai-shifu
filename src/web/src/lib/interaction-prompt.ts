/** Remove only the metadata-backed compatibility prefix, leaving authored content intact. */
export const stripInteractionPromptPrefix = (
  content: string,
  prompt: unknown,
): string => {
  if (typeof prompt !== 'string' || !prompt.trim()) {
    return content;
  }

  const prefix =
    Array.from(prompt)
      .map(char => `&#${char.codePointAt(0)};`)
      .join('') + '\n\n';
  return content.startsWith(prefix) ? content.slice(prefix.length) : content;
};
