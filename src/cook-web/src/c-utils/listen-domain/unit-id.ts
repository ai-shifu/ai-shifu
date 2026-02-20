export type ListenUnitId = `${string}:${number}`;

export const normalizeListenUnitPosition = (raw: unknown): number => {
  const value = Number(raw ?? 0);
  if (!Number.isFinite(value) || value < 0) {
    return 0;
  }
  return Math.floor(value);
};

export const buildListenUnitId = (
  blockBid: string,
  position?: unknown,
): ListenUnitId => {
  const normalizedBid = (blockBid || '').trim();
  const normalizedPosition = normalizeListenUnitPosition(position);
  return `${normalizedBid}:${normalizedPosition}` as ListenUnitId;
};

export const parseListenUnitId = (
  unitId: string,
): { blockBid: string; position: number } | null => {
  if (!unitId) {
    return null;
  }

  const separatorIndex = unitId.lastIndexOf(':');
  if (separatorIndex <= 0 || separatorIndex >= unitId.length - 1) {
    return null;
  }

  const blockBid = unitId.slice(0, separatorIndex);
  const rawPosition = unitId.slice(separatorIndex + 1);
  const parsedPosition = Number(rawPosition);
  if (!blockBid || !Number.isFinite(parsedPosition) || parsedPosition < 0) {
    return null;
  }

  return {
    blockBid,
    position: Math.floor(parsedPosition),
  };
};
