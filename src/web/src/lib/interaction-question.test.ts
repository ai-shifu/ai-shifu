import { stripInteractionQuestionPrefix } from './interaction-question';

const controls = '?[%{{answer}} First//a | Second//b | ...Your response]';

it('removes only an exact decimal-entity compatibility prefix', () => {
  expect(
    stripInteractionQuestionPrefix('&#81;&#63;\n\n' + controls, 'Q?'),
  ).toBe(controls);
  expect(stripInteractionQuestionPrefix(controls, 'Q?')).toBe(controls);
  expect(
    stripInteractionQuestionPrefix(
      stripInteractionQuestionPrefix('&#81;&#63;\n\n' + controls, 'Q?'),
      'Q?',
    ),
  ).toBe(controls);
});

it('uses Unicode code points and preserves leading whitespace in the question', () => {
  expect(
    stripInteractionQuestionPrefix(
      '&#32;&#128105;&#127997;&#8205;&#128187;&#10;\n\n' + controls,
      ' 👩🏽‍💻\n',
    ),
  ).toBe(controls);
});

it('never authorizes a compatibility prefix from blank metadata', () => {
  const content = '&#32;&#10;\n\n' + controls;
  expect(stripInteractionQuestionPrefix(content, ' \n')).toBe(content);
});

it.each([undefined, null, '', 42, { text: 'Q?' }])(
  'preserves wire content when question metadata is unavailable: %p',
  question => {
    const content = '&#81;&#63;\n\n' + controls;
    expect(stripInteractionQuestionPrefix(content, question)).toBe(content);
  },
);

it.each([
  'Q?\n\n',
  '&#81;&#63;\n',
  '&#81;&#63;\n\n ',
  '&#081;&#63;\n\n',
  '&#x51;&#63;\n\n',
  'before &#81;&#63;\n\n',
  '&#81;&#33;\n\n',
])('never decodes, trims or searches authored content: %p', prefix => {
  const content = prefix + controls;
  const expected = prefix === '&#81;&#63;\n\n ' ? ' ' + controls : content;
  expect(stripInteractionQuestionPrefix(content, 'Q?')).toBe(expected);
});

it('keeps a sensitive authored placeholder and answer syntax intact', () => {
  const content =
    '?[%{{secret_answer}} ...Do not share your password: {{hint}}]';
  expect(
    stripInteractionQuestionPrefix(content, 'Do not share your password'),
  ).toBe(content);
  expect(stripInteractionQuestionPrefix('&#81;&#63;\n\n' + content, 'Q?')).toBe(
    content,
  );
});
