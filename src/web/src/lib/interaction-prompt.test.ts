import { stripInteractionPromptPrefix } from './interaction-prompt';

const controls = '?[%{{answer}} First//a | Second//b | ...Your response]';

it('removes only an exact decimal-entity compatibility prefix', () => {
  expect(stripInteractionPromptPrefix('&#81;&#63;\n\n' + controls, 'Q?')).toBe(
    controls,
  );
  expect(stripInteractionPromptPrefix(controls, 'Q?')).toBe(controls);
  expect(
    stripInteractionPromptPrefix(
      stripInteractionPromptPrefix('&#81;&#63;\n\n' + controls, 'Q?'),
      'Q?',
    ),
  ).toBe(controls);
});

it('uses Unicode code points and preserves leading whitespace in the prompt', () => {
  expect(
    stripInteractionPromptPrefix(
      '&#32;&#128105;&#127997;&#8205;&#128187;&#10;\n\n' + controls,
      ' 👩🏽‍💻\n',
    ),
  ).toBe(controls);
});

it('never authorizes a compatibility prefix from blank metadata', () => {
  const content = '&#32;&#10;\n\n' + controls;
  expect(stripInteractionPromptPrefix(content, ' \n')).toBe(content);
});

it.each([undefined, null, '', 42, { text: 'Q?' }])(
  'preserves wire content when prompt metadata is unavailable: %p',
  prompt => {
    const content = '&#81;&#63;\n\n' + controls;
    expect(stripInteractionPromptPrefix(content, prompt)).toBe(content);
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
  expect(stripInteractionPromptPrefix(content, 'Q?')).toBe(expected);
});

it('keeps a sensitive authored placeholder and answer syntax intact', () => {
  const content =
    '?[%{{secret_answer}} ...Do not share your password: {{hint}}]';
  expect(
    stripInteractionPromptPrefix(content, 'Do not share your password'),
  ).toBe(content);
  expect(stripInteractionPromptPrefix('&#81;&#63;\n\n' + content, 'Q?')).toBe(
    content,
  );
});
