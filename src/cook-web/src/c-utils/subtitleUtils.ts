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

export const stripDisallowedSubtitleTrailingPunctuation = (text: string) => {
  const trimmedText = text.trimEnd();

  if (!trimmedText) {
    return trimmedText;
  }

  let suffix = '';
  let cursor = trimmedText.length;

  // Preserve trailing paired closers such as quotes or brackets.
  while (cursor > 0) {
    const currentChar = trimmedText[cursor - 1];

    if (!isTrailingSubtitlePairCloser(currentChar)) {
      break;
    }

    suffix = `${currentChar}${suffix}`;
    cursor -= 1;
  }

  let content = trimmedText.slice(0, cursor);

  while (content) {
    if (isAllowedSubtitleEnding(content)) {
      break;
    }

    const currentChar = content[content.length - 1];
    if (!isPunctuationChar(currentChar)) {
      break;
    }

    content = content.slice(0, -1).trimEnd();
  }

  return `${content}${suffix}`;
};
