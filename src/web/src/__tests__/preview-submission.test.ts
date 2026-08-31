import {
  buildPreviewInteractionUserInput,
  resolvePreviewGeneratedBlockBid,
  resolvePreviewRegenerateFallbackBlockIndex,
  resolvePreviewRegenerateStartIndex,
  resolvePreviewRequestBlockIndex,
} from '@/components/lesson-preview/preview-submission';
import { ChatContentItemType } from '@/c-types/chatUi';

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

  it('resolves regenerate truncation to the first item of the same block', () => {
    expect(
      resolvePreviewRegenerateStartIndex(
        [
          { element_bid: 'block-0-a', generated_block_bid: '0' },
          { element_bid: 'block-1-a', generated_block_bid: '1' },
          { element_bid: 'block-1-b', generated_block_bid: '1' },
          { element_bid: 'block-2-a', generated_block_bid: '2' },
        ],
        2,
      ),
    ).toBe(1);
  });

  it('falls back to the target index when the block bid is missing', () => {
    expect(
      resolvePreviewRegenerateStartIndex(
        [{ element_bid: 'preview-runtime-1', generated_block_bid: '' }],
        0,
      ),
    ).toBe(0);
  });

  it('prefers the item element_index when resolving regenerate fallback block index', () => {
    expect(
      resolvePreviewRegenerateFallbackBlockIndex(
        [
          { type: ChatContentItemType.CONTENT, element_index: 0 },
          { type: ChatContentItemType.LIKE_STATUS },
          { type: ChatContentItemType.CONTENT, element_index: 3 },
        ],
        2,
      ),
    ).toBe(3);
  });

  it('counts only actionable items when element_index is missing', () => {
    expect(
      resolvePreviewRegenerateFallbackBlockIndex(
        [
          { type: ChatContentItemType.CONTENT },
          { type: ChatContentItemType.LIKE_STATUS },
          { type: ChatContentItemType.ASK },
          { type: ChatContentItemType.INTERACTION },
          { type: ChatContentItemType.CONTENT },
        ],
        4,
      ),
    ).toBe(2);
  });

  it('returns 0 when resolving regenerate fallback block index with empty items', () => {
    expect(resolvePreviewRegenerateFallbackBlockIndex([], 0)).toBe(0);
  });

  it('clamps out-of-range block indexes before resolving regenerate fallback block index', () => {
    expect(
      resolvePreviewRegenerateFallbackBlockIndex(
        [
          { type: ChatContentItemType.CONTENT, element_index: 0 },
          { type: ChatContentItemType.INTERACTION, element_index: 1 },
        ],
        99,
      ),
    ).toBe(1);

    expect(
      resolvePreviewRegenerateFallbackBlockIndex(
        [
          { type: ChatContentItemType.LIKE_STATUS },
          { type: ChatContentItemType.CONTENT, element_index: 4 },
        ],
        -2,
      ),
    ).toBe(0);
  });
});
