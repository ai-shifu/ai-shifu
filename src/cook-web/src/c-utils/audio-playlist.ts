export const normalizeAudioItemList = <
  T extends { generated_block_bid?: string; audioPlaybackBid?: string },
>(
  items: T[],
  getKey: (item: T) => string | undefined = item =>
    item.audioPlaybackBid || item.generated_block_bid,
): T[] => {
  const order: string[] = [];
  const mapping = new Map<string, T>();
  items.forEach(item => {
    const key = getKey(item);
    if (!key) {
      return;
    }
    if (!mapping.has(key)) {
      order.push(key);
    }
    mapping.set(key, item);
  });
  return order.map(key => mapping.get(key)!).filter(Boolean);
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
