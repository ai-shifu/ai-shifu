export const resolvePreviewRequestBlockIndex = (
  generatedBlockBid: string,
  fallbackBlockIndex = 0,
): number => {
  const parsedValue = Number.parseInt(generatedBlockBid, 10);
  return Number.isNaN(parsedValue) ? fallbackBlockIndex : parsedValue;
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
