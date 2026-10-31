import type {
  DebugRunParams,
  DebugVariableValues,
} from '@/types/debug-session';
import type { ChatContentItem } from '@/types/chatUi';
import { normalizeVariableName } from 'remark-flow';

export const resolveDebugRequestBlockIndex = (
  generatedBlockBid: string,
  fallbackBlockIndex = 0,
): number => {
  // 1.0 uses decimal block indices; 2.0 uses opaque generated block IDs.
  // parseInt accepts a numeric prefix of a UUID and can skip the next request.
  return /^\d+$/.test(generatedBlockBid)
    ? Number(generatedBlockBid)
    : fallbackBlockIndex;
};

export const resolveDebugRegenerationStartIndex = (
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

export const resolveDebugRegenerationBlockIndex = (
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

export const buildDebugInteractionInput = (
  variableName: string,
  values: string[],
): Record<string, string[]> | undefined => {
  if (!values.length) {
    return undefined;
  }
  const normalizedVariableName = normalizeVariableName(variableName);
  return {
    [normalizedVariableName || 'input']: values,
  };
};

export const resolveDebugGeneratedBlockBid = ({
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

export const buildDebugContinuationParams = ({
  currentParams,
  latestMdflow,
  blockIndex,
  variableValues,
  userInput,
}: {
  currentParams: DebugRunParams;
  latestMdflow: string;
  blockIndex: number;
  variableValues: DebugVariableValues;
  userInput?: Record<string, string[]>;
}): DebugRunParams => {
  const nextParams: DebugRunParams = {
    ...currentParams,
    mdflow: latestMdflow,
    blockIndex,
    variableValues,
  };

  if (userInput) {
    nextParams.userInput = userInput;
  } else if ('userInput' in nextParams) {
    delete nextParams.userInput;
  }

  return nextParams;
};
