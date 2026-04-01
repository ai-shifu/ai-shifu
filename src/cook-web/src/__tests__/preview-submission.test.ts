import {
  buildPreviewInteractionUserInput,
  resolvePreviewGeneratedBlockBid,
  resolvePreviewRequestBlockIndex,
} from '@/components/lesson-preview/preview-submission';

describe('preview submission helpers', () => {
  it('falls back to current block_index when generated_block_bid is not numeric', () => {
    expect(resolvePreviewRequestBlockIndex('preview-feedback', 5)).toBe(5);
  });

  it('parses numeric generated_block_bid values into preview block indexes', () => {
    expect(resolvePreviewRequestBlockIndex('3', 7)).toBe(3);
  });

  it('uses input as fallback user_input key when variable name is empty', () => {
    expect(buildPreviewInteractionUserInput('', ['A'])).toEqual({
      input: ['A'],
    });
  });

  it('keeps backend generated_block_bid when preview item has a runtime element id', () => {
    expect(
      resolvePreviewGeneratedBlockBid({
        elementGeneratedBlockBid: '5',
        responseGeneratedBlockBid: 'fallback',
        fallbackBid: 'preview-element-1',
      }),
    ).toBe('5');
  });

  it('falls back to the top-level event block bid before using the item bid', () => {
    expect(
      resolvePreviewGeneratedBlockBid({
        responseGeneratedBlockBid: '7',
        fallbackBid: 'preview-element-1',
      }),
    ).toBe('7');
  });
});
