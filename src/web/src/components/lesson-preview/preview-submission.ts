import type { ChatContentItem } from '@/types/chatUi';

export const resolvePreviewRequestBlockIndex = (
  generatedBlockBid: string,
  fallbackBlockIndex = 0,
): number => {
  // 1.0 uses decimal block indices; 2.0 uses opaque generated block IDs.
  // parseInt accepts a numeric prefix of a UUID and can skip the next request.
  return /^\d+$/.test(generatedBlockBid)
    ? Number(generatedBlockBid)
    : fallbackBlockIndex;
};

export const resolvePreviewRegenerateStartIndex = (
  items: Pick<ChatContentItem, 'generated_block_bid' | 'element_bid'>[],
  targetIndex: number,
): number => {
  if (targetIndex < 0 || targetIndex >= items.length) {
    return -1;
  }

  const targetItem = items[targetIndex];
  const targetGeneratedBlockBid =
    targetItem.generated_block_bid || targetItem.element_bid || '';
  if (!targetGeneratedBlockBid) {
    return targetIndex;
  }

  const firstBlockIndex = items.findIndex(
    item =>
      (item.generated_block_bid || item.element_bid || '') ===
      targetGeneratedBlockBid,
  );
  return firstBlockIndex === -1 ? targetIndex : firstBlockIndex;
};

export const resolvePreviewRegenerateFallbackBlockIndex = (
  items: Pick<ChatContentItem, 'type' | 'element_index'>[],
  blockStartIndex: number,
): number => {
  if (!items.length) {
    return 0;
  }

  const resolvedIndex = Math.min(
    Math.max(blockStartIndex, 0),
    items.length - 1,
  );
  const targetItem = items[resolvedIndex];
  if (typeof targetItem?.element_index === 'number') {
    return targetItem.element_index;
  }

  return items.slice(0, resolvedIndex).filter(item => {
    return item.type === 'content' || item.type === 'interaction';
  }).length;
};

export const buildPreviewInteractionUserInput = (
  variableName: string,
  values: string[],
): Record<string, string[]> | undefined => {
  if (!values.length) {
    return undefined;
  }
  const normalizedVariableName = variableName.trim();
  return {
    [normalizedVariableName || 'input']: values,
  };
};

export const resolvePreviewGeneratedBlockBid = ({
  elementGeneratedBlockBid,
  responseGeneratedBlockBid,
  fallbackBid,
}: {
  elementGeneratedBlockBid?: unknown;
  responseGeneratedBlockBid?: unknown;
  fallbackBid: string;
}): string => {
  if (
    typeof elementGeneratedBlockBid === 'string' &&
    elementGeneratedBlockBid.trim()
  ) {
    return elementGeneratedBlockBid;
  }
  if (
    typeof responseGeneratedBlockBid === 'string' &&
    responseGeneratedBlockBid.trim()
  ) {
    return responseGeneratedBlockBid;
  }
  return fallbackBid;
};
