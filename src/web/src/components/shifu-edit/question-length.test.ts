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

  test('previews whole code points', () => {
    expect(previewQuestion('😀'.repeat(30))).toBe('😀'.repeat(20));
  });
});
