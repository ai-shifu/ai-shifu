const CUSTOM_BUTTON_AFTER_CONTENT_TAG = '<custom-button-after-content>';
const CUSTOM_BUTTON_AFTER_CONTENT_REGEX =
  /<custom-button-after-content>[\s\S]*?<\/custom-button-after-content>/g;

type LegacyBlockCompatItem = {
  element_bid?: string;
  generated_block_bid?: string;
  parent_element_bid?: string;
  parent_block_bid?: string;
  ask_list?: LegacyBlockCompatItem[];
  type?: string;
};

export const appendCustomButtonAfterContent = (
  content: string | undefined,
  buttonMarkup: string,
): string => {
  const baseContent = content ?? '';

  if (!buttonMarkup) {
    return baseContent;
  }

  if (baseContent.includes(CUSTOM_BUTTON_AFTER_CONTENT_TAG)) {
    return baseContent;
  }

  const trimmedContent = baseContent.trimEnd();
  const endsWithCodeFence =
    trimmedContent.endsWith('```') || trimmedContent.endsWith('~~~');
  const needsLineBreak =
    endsWithCodeFence && !baseContent.endsWith('\n') ? '\n' : '';

  return baseContent + needsLineBreak + buttonMarkup;
};

export const hasCustomButtonAfterContent = (
  content?: string | null,
): boolean => {
  return Boolean(content?.includes(CUSTOM_BUTTON_AFTER_CONTENT_TAG));
};

export const stripCustomButtonAfterContent = (
  content?: string | null,
): string | null | undefined => {
  if (!content) {
    return content;
  }
  if (!hasCustomButtonAfterContent(content)) {
    return content;
  }
  // Remove ask button markup from listen mode content.
  return content.replace(CUSTOM_BUTTON_AFTER_CONTENT_REGEX, '').trimEnd();
};

export const syncCustomButtonAfterContent = ({
  content,
  buttonMarkup,
  shouldShowButton,
}: {
  content?: string | null;
  buttonMarkup: string;
  shouldShowButton: boolean;
}): string => {
  const baseContent = content ?? '';

  if (shouldShowButton) {
    return appendCustomButtonAfterContent(baseContent, buttonMarkup);
  }

  return stripCustomButtonAfterContent(baseContent) ?? '';
};

export const inheritCustomButtonAfterContent = ({
  nextContent,
  previousContent,
  buttonMarkup,
}: {
  nextContent?: string | null;
  previousContent?: string | null;
  buttonMarkup: string;
}): string => {
  const resolvedNextContent = nextContent ?? '';

  if (!hasCustomButtonAfterContent(previousContent)) {
    return resolvedNextContent;
  }

  return appendCustomButtonAfterContent(resolvedNextContent, buttonMarkup);
};

export const normalizeLegacyBlockCompatItem = <T extends LegacyBlockCompatItem>(
  item: T,
): T => {
  const elementBid = item.element_bid || item.generated_block_bid || '';
  const generatedBlockBid = item.generated_block_bid || item.element_bid || '';
  const parentElementBid =
    item.parent_element_bid || item.parent_block_bid || undefined;
  const parentBlockBid =
    item.parent_block_bid || item.parent_element_bid || undefined;
  const normalizedAskList = Array.isArray(item.ask_list)
    ? item.ask_list.map(normalizeLegacyBlockCompatItem)
    : item.ask_list;
  const hasAskListChanged = normalizedAskList !== item.ask_list;
  const hasCompatChanged =
    elementBid !== (item.element_bid || '') ||
    generatedBlockBid !== (item.generated_block_bid || '') ||
    parentElementBid !== item.parent_element_bid ||
    parentBlockBid !== item.parent_block_bid;

  if (!hasCompatChanged && !hasAskListChanged) {
    return item;
  }

  return {
    ...item,
    element_bid: elementBid,
    generated_block_bid: generatedBlockBid,
    parent_element_bid: parentElementBid,
    parent_block_bid: parentBlockBid,
    ...(hasAskListChanged ? { ask_list: normalizedAskList } : {}),
  };
};

export const normalizeLegacyBlockCompatList = <T extends LegacyBlockCompatItem>(
  items: T[],
): T[] => items.map(normalizeLegacyBlockCompatItem);
