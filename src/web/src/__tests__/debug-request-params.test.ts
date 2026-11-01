import {
  buildDebugInteractionInput,
  resolveDebugGeneratedBlockBid,
  resolveDebugRequestBlockIndex,
} from '@/components/lesson-debug/debug-request-params';

jest.mock('remark-flow', () =>
  jest.requireActual('remark-flow/dist/variable-name'),
);

describe('preview submission helpers', () => {
  it.each([
    ['你的性别是？', '你的性别是？'],
    ['gender?', 'gender?'],
    ['\u0085key\u0085', 'key'],
    ['\ufeffkey\ufeff', '\ufeffkey\ufeff'],
    ['\ufeff', '\ufeff'],
    ['  user  name  ', 'user  name'],
    [' Which [path] | level//hint...? ', 'Which [path] | level//hint...?'],
    [' a} ', 'a}'],
  ])('normalizes %s with the teaching engine key rules', (source, key) => {
    expect(buildDebugInteractionInput(source, ['女'])).toEqual({
      [key]: ['女'],
    });
  });
  it('falls back to current block_index when generated_block_bid is not numeric', () => {
    expect(resolveDebugRequestBlockIndex('preview-feedback', 5)).toBe(5);
  });

  it('parses numeric generated_block_bid values into preview block indexes', () => {
    expect(resolveDebugRequestBlockIndex('3', 7)).toBe(3);
  });

  it('does not parse the numeric prefix of an opaque 2.0 block ID', () => {
    expect(
      resolveDebugRequestBlockIndex('68bbca55db4b4134a5502a641aa0ca04', 1),
    ).toBe(1);
  });

  it('uses input as fallback user_input key when variable name is empty', () => {
    expect(buildDebugInteractionInput('', ['A'])).toEqual({
      input: ['A'],
    });
  });

  it('keeps backend generated_block_bid when preview item has a runtime element id', () => {
    expect(
      resolveDebugGeneratedBlockBid({
        elementGeneratedBlockBid: '5',
        responseGeneratedBlockBid: 'fallback',
        fallbackBid: 'preview-element-1',
      }),
    ).toBe('5');
  });

  it('falls back to the top-level event block bid before using the item bid', () => {
    expect(
      resolveDebugGeneratedBlockBid({
        responseGeneratedBlockBid: '7',
        fallbackBid: 'preview-element-1',
      }),
    ).toBe('7');
  });
});
