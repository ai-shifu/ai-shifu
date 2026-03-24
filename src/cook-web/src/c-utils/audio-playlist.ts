export const normalizeAudioItemList = <
  T extends { generated_block_bid?: string },
>(
  items: T[],
): T[] => {
  const order: string[] = [];
  const mapping = new Map<string, T>();
  items.forEach(item => {
    const bid = item.generated_block_bid;
    if (!bid) {
      return;
    }
    if (!mapping.has(bid)) {
      order.push(bid);
    }
    mapping.set(bid, item);
  });
  return order.map(bid => mapping.get(bid)!).filter(Boolean);
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
