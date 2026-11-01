import type {
  DebugRunParams,
  DebugVariableValues,
} from '@/types/debug-session';
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
