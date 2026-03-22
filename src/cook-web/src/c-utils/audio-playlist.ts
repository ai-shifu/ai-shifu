type AudioIdentityItem = {
  element_bid?: string;
  generated_block_bid?: string;
};

export const resolveAudioItemKey = <T extends AudioIdentityItem>(
  item?: T | null,
) => item?.element_bid || item?.generated_block_bid || null;

export const normalizeAudioItemList = <T extends AudioIdentityItem>(
  items: T[],
): T[] => {
  const order: string[] = [];
  const mapping = new Map<string, T>();
  items.forEach(item => {
    const itemKey = resolveAudioItemKey(item);
    if (!itemKey) {
      return;
    }
    if (!mapping.has(itemKey)) {
      order.push(itemKey);
    }
    mapping.set(itemKey, item);
  });
  return order.map(itemKey => mapping.get(itemKey)!).filter(Boolean);
};

export const getNextIndex = (currentIndex: number, listLength: number) => {
  if (listLength <= 0) {
    return 0;
  }
  return currentIndex + 1 < listLength ? currentIndex + 1 : currentIndex;
};

export const getPrevIndex = (currentIndex: number, listLength: number) => {
  if (listLength <= 0) {
    return 0;
  }
  return currentIndex > 0 ? currentIndex - 1 : currentIndex;
};

export const sortAudioSegments = <T extends { segmentIndex: number }>(
  segments: T[] = [],
): T[] => [...segments].sort((a, b) => a.segmentIndex - b.segmentIndex);
