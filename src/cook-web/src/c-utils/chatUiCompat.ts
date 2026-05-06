type LegacyBlockCompatItem = {
  element_bid?: string;
  generated_block_bid?: string;
  parent_element_bid?: string;
  parent_block_bid?: string;
  ask_list?: LegacyBlockCompatItem[];
  type?: string;
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
