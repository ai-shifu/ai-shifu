const TRAILING_SUBTITLE_PAIR_CLOSERS = new Set([
  '"',
  "'",
  '”',
  '’',
  '）',
  ')',
  ']',
  '】',
  '}',
  '》',
  '〉',
  '」',
  '』',
  '〕',
  '〗',
  '〙',
  '〛',
]);

const ALLOWED_SUBTITLE_ENDING_PATTERN = /(?:[?!？！]+|\.{3,}|…+|⋯+)$/u;
const PUNCTUATION_CHAR_PATTERN = /\p{P}/u;

const isTrailingSubtitlePairCloser = (char: string) =>
  TRAILING_SUBTITLE_PAIR_CLOSERS.has(char);

const isAllowedSubtitleEnding = (text: string) =>
  ALLOWED_SUBTITLE_ENDING_PATTERN.test(text);

const isPunctuationChar = (char: string) => PUNCTUATION_CHAR_PATTERN.test(char);
const isWhitespaceChar = (char: string) => /\s/u.test(char);

export const stripDisallowedSubtitleTrailingPunctuation = (text: string) => {
  const trimmedText = text.trimEnd();

  if (!trimmedText) {
    return trimmedText;
  }

  let suffix = '';
  let cursor = trimmedText.length;

  // Walk backwards so paired closers stay preserved even if removable
  // punctuation appears after them, such as `。”` or `），`.
  while (cursor > 0) {
    const currentChar = trimmedText[cursor - 1];
    const currentContent = trimmedText.slice(0, cursor);

    if (isTrailingSubtitlePairCloser(currentChar)) {
      suffix = `${currentChar}${suffix}`;
      cursor -= 1;
      continue;
    }

    if (isAllowedSubtitleEnding(currentContent)) {
      break;
    }

    if (!isPunctuationChar(currentChar)) {
      break;
    }

    cursor -= 1;

    while (cursor > 0 && isWhitespaceChar(trimmedText[cursor - 1])) {
      cursor -= 1;
    }
  }

  const content = trimmedText.slice(0, cursor).trimEnd();
  return `${content}${suffix}`;
};
