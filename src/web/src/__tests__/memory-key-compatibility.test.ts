import { createInteractionParser, extractVariableNames } from 'remark-flow';
import { buildDebugInteractionUserInput } from '@/components/lesson-debug/debug-submission';
import { resolveInteractionSubmission } from '@/lib/interaction-user-input';

// Exercise the packaged parser and helpers while avoiding Jest's unrelated ESM plugin loader.
jest.mock('remark-flow', () => ({
  ...jest.requireActual('remark-flow/dist/interaction-parser'),
  ...jest.requireActual('remark-flow/dist/variable-name'),
}));

describe.each(['%', ''])('authored %s{{key}} compatibility', marker => {
  const parser = createInteractionParser();

  it.each([
    '你的性别是？',
    'gender?',
    '性别:？',
    '名字（可选）',
    'learner_name',
    '性别',
    'a|b',
    'a...b',
    'a//b',
    '😀?',
    '\ufeffkey\ufeff',
    '\ufeff',
    'user name',
    'user  name',
    'Which [path] | level//hint...?',
    'a{b}c',
    'a}',
    '}',
    'outer{{inner',
    '"name"',
    'path\\',
    '<b>name</b>',
  ])('preserves %s from parsing through named answer submission', key => {
    const source = `?[${marker}{{ ${key} }} 男 | 女 | 秘密]`;
    const interaction = parser.parseToRemarkFormat(source);

    expect(extractVariableNames(`${source}\n{{ ${key} }}`)).toEqual([key]);
    expect(interaction).toEqual({
      variableName: key,
      buttonTexts: ['男', '女', '秘密'],
      buttonValues: ['男', '女', '秘密'],
      isMultiSelect: false,
    });
    const { values } = resolveInteractionSubmission({
      variableName: interaction.variableName,
      buttonText: interaction.buttonValues![1],
    });

    expect(
      buildDebugInteractionUserInput(interaction.variableName!, values),
    ).toEqual({ [key]: ['女'] });
  });

  it('keeps existing display values and multiple selection semantics', () => {
    expect(
      parser.parseToRemarkFormat(
        `?[${marker}{{skills}} 前端//web || 后端//api]`,
      ),
    ).toEqual({
      variableName: 'skills',
      buttonTexts: ['前端', '后端'],
      buttonValues: ['web', 'api'],
      isMultiSelect: true,
    });
  });

  it.each([
    `Show \`{{\` then ?[${marker}{{ q }} A|B]`,
    `Show \`{{\`\n?[${marker}{{ q }} A|B]`,
    `Text <span title="{{">\n?[${marker}{{ q }} A|B]`,
    `Text <span title="before\n{{">\n?[${marker}{{ q }} A|B]`,
    `\\{{ example ?[${marker}{{ q }} A|B]`,
    `Show \\{{ not a variable }} then ?[${marker}{{ q }} A|B]`,
  ])('extracts preview keys after a literal marker example: %s', source => {
    expect(extractVariableNames(source)).toEqual(['q']);
  });
});
