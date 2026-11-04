/** Remove only the metadata-backed compatibility prefix, leaving authored content intact. */
export const stripInteractionQuestionPrefix = (
  content: string,
  question: unknown,
): string => {
  if (typeof question !== 'string' || !question.trim()) {
    return content;
  }

  const prefix =
    Array.from(question)
      .map(char => `&#${char.codePointAt(0)};`)
      .join('') + '\n\n';
  return content.startsWith(prefix) ? content.slice(prefix.length) : content;
};
