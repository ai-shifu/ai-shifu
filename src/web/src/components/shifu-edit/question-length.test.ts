import {
  countQuestionLength,
  findOverlongQuestions,
  previewQuestion,
} from './question-length';

jest.mock('remark-flow', () =>
  jest.requireActual('remark-flow/dist/variable-name'),
);

describe('question length limit', () => {
  test('counts Unicode code points like the backend', () => {
    expect(countQuestionLength('😀问q')).toBe(3);
  });

  test('flags only distinct questions over the limit', () => {
    const overlong = 'q'.repeat(201);
    const content = [
      `?[{{${overlong}}} ...Answer]`,
      `Again {{ ${overlong} }}`,
      `?[%{{${'问'.repeat(200)}}} Yes | No]`,
      `{{${'😀'.repeat(201)}}}`,
    ].join('\n\n');

    expect(findOverlongQuestions(content)).toEqual([
      { name: overlong, length: 201 },
      { name: '😀'.repeat(201), length: 201 },
    ]);
  });

  test('returns nothing for empty or compliant content', () => {
    expect(findOverlongQuestions('')).toEqual([]);
    expect(findOverlongQuestions(`{{${'q'.repeat(200)}}}`)).toEqual([]);
  });

  test('ignores fenced code blocks and HTML comments like the backend', () => {
    const overlong = 'q'.repeat(201);
    const content = [
      '```md',
      `{{${overlong}}}`,
      '```',
      `<!-- {{${overlong}}} -->`,
      '<!--',
      `?[{{${overlong}}} ...Answer]`,
      '-->',
      '~~~~',
      '~~~',
      `{{${overlong}}}`,
      '~~~~',
    ].join('\n');

    expect(findOverlongQuestions(content)).toEqual([]);
    expect(findOverlongQuestions(`${content}\n\n{{${overlong}}}`)).toEqual([
      { name: overlong, length: 201 },
    ]);
  });

  test('measures comment syntax inside a question like the backend', () => {
    const name = `${'q'.repeat(195)}<!--note-->`;

    expect(findOverlongQuestions(`?[{{${name}}} ...Answer]`)).toEqual([
      { name, length: 206 },
    ]);
    expect(
      findOverlongQuestions(`{{${'q'.repeat(150)}-->}} {{${'q'.repeat(201)}}}`),
    ).toEqual([{ name: 'q'.repeat(201), length: 201 }]);
  });

  test('does not open a fence inside an HTML comment', () => {
    const overlong = 'q'.repeat(201);

    expect(
      findOverlongQuestions(
        ['<!--', '```', '-->', `{{${overlong}}}`].join('\n'),
      ),
    ).toEqual([{ name: overlong, length: 201 }]);
    expect(
      findOverlongQuestions(
        ['```', '<!--', '```', `{{${overlong}}}`].join('\n'),
      ),
    ).toEqual([{ name: overlong, length: 201 }]);
  });

  test('previews whole code points', () => {
    expect(previewQuestion('😀'.repeat(30))).toBe('😀'.repeat(20));
  });
});
