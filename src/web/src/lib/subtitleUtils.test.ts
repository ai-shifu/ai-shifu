import { stripDisallowedSubtitleTrailingPunctuation as strip } from './subtitleUtils';

describe('stripDisallowedSubtitleTrailingPunctuation', () => {
  it.each([
    ['Arabic', 'هل فهمت؟'],
    ['Armenian question', 'Այո՞'],
    ['Armenian exclamation', 'Այո՜'],
    ['Ethiopic', 'ለምን፧'],
    ['Limbu', 'ᤕᤠ᥄'],
    ['Nko', 'ߒߞߏ߹'],
    ['Vai', 'ꕉ꘏'],
    ['Bamum', 'ꚠ꛷'],
    ['Chakma', '𑄃𑅃'],
    ['Adlam', '𞤀𞥟'],
    ['Greek question code point', 'Πώς είσαι\u037e'],
    ['combined question and exclamation', 'Really‼⁇⁈⁉‽'],
    ['small forms', 'Really﹖﹗'],
    ['vertical forms', 'Really︕︖'],
    ['fullwidth forms', '真的吗？！'],
  ])('preserves %s endings', (_language, text) => {
    expect(strip(text)).toBe(text);
  });

  it.each([
    ['«Bonjour.»', '«Bonjour»'],
    ['«Vraiment ?»', '«Vraiment ?»'],
    ['« Bonjour. »', '« Bonjour »'],
    ['«\u00a0Bonjour.\u00a0»', '«\u00a0Bonjour\u00a0»'],
    ['„Hallo.“', '„Hallo“'],
    ['»Hallo.«', '»Hallo«'],
    ['‹Bonjour.›', '‹Bonjour›'],
    ['（«Bonjour.»），', '（«Bonjour»）'],
    ['「你好。」', '「你好」'],
    ['问号保留？”。 ', '问号保留？”'],
    ['〈Hello〉。', '〈Hello〉'],
    ['﴿مرحبا.﴾', '﴿مرحبا﴾'],
  ])('preserves closing punctuation in %s', (text, expected) => {
    expect(strip(text)).toBe(expected);
  });

  it.each([
    ['نعم۔', 'نعم'],
    ['Ինչպե՞ս ես։', 'Ինչպե՞ս ես'],
    ['ठीक है।', 'ठीक है'],
    ['ሰላም።', 'ሰላም'],
    ['𑀅\u{11047}', '𑀅'],
    ['First;', 'First'],
    ['مرحبا؛', 'مرحبا'],
    ['你好，。：', '你好'],
    ['Hello . , ', 'Hello'],
    ['Hello..', 'Hello'],
    ['😀。', '😀'],
    ['', ''],
    [' \t\n', ''],
    ['。،\u{11047}', ''],
  ])('removes ordinary trailing punctuation in %s', (text, expected) => {
    expect(strip(text)).toBe(expected);
  });

  it.each([
    'Wait...',
    'Wait....',
    '等等……',
    'Wait⋯',
    'Wait᠁',
    'Wait︙',
    'Family 👨‍👩‍👧‍👦',
    'Combining e\u0301',
    'Unpunctuated text',
  ])('preserves ellipses and non-punctuation text in %s', text => {
    expect(strip(`${text}。 \n`)).toBe(text);
  });
});
