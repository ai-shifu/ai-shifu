// Unicode has no question/exclamation property. These are the punctuation
// characters named QUESTION, EXCLAMATION, INTERROBANG, or ELLIPSIS in
// https://www.unicode.org/Public/17.0.0/ucd/UnicodeData.txt.
// Keep U+037E distinct: ASCII semicolons retain their existing display policy.
const ALLOWED_SUBTITLE_ENDINGS = new Set(
  Array.from('!?¡¿\u037e՜՞؟߹፧᠁᥄᥅…‼‽⁇⁈⁉' + '⳺⳻⸘⸮⹓⹔꘏꛷︕︖︙﹖﹗！？𑅃𖺚𞥞𞥟'),
);
// Quote orientation varies by language, so preserve both orientations at the end.
const TRAILING_SUBTITLE_CLOSER_PATTERN = /[\p{Pe}\p{Pf}\p{Quotation_Mark}]/u;
const PUNCTUATION_CHAR_PATTERN = /\p{P}/u;

const isTrailingSubtitlePairCloser = (char: string) =>
  TRAILING_SUBTITLE_CLOSER_PATTERN.test(char);

const isAllowedSubtitleEnding = (characters: string[], cursor: number) =>
  ALLOWED_SUBTITLE_ENDINGS.has(characters[cursor - 1]) ||
  (characters[cursor - 1] === '.' &&
    characters[cursor - 2] === '.' &&
    characters[cursor - 3] === '.');

const isPunctuationChar = (char: string) => PUNCTUATION_CHAR_PATTERN.test(char);
const isWhitespaceChar = (char: string) => /\s/u.test(char);

export const stripDisallowedSubtitleTrailingPunctuation = (text: string) => {
  const trimmedText = text.trimEnd();

  if (!trimmedText) {
    return trimmedText;
  }

  const characters = Array.from(trimmedText);
  const suffix: string[] = [];
  let cursor = characters.length;

  // Walk backwards so paired closers stay preserved even if removable
  // punctuation appears after them, such as `。”` or `），`.
  while (cursor > 0) {
    const currentChar = characters[cursor - 1];

    if (
      isTrailingSubtitlePairCloser(currentChar) ||
      (suffix.length > 0 && isWhitespaceChar(currentChar))
    ) {
      // Preserve spacing inside quotes, including French non-breaking spaces.
      suffix.push(currentChar);
      cursor -= 1;
      continue;
    }

    if (isAllowedSubtitleEnding(characters, cursor)) {
      break;
    }

    if (!isPunctuationChar(currentChar)) {
      break;
    }

    cursor -= 1;

    while (cursor > 0 && isWhitespaceChar(characters[cursor - 1])) {
      cursor -= 1;
    }
  }

  const content = characters.slice(0, cursor).join('').trimEnd();
  return `${content}${suffix.reverse().join('')}`;
};
