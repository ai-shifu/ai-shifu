type ShifuDetailPayload = {
  can_publish?: boolean;
  canPublish?: boolean;
};

export const normalizeShifuDetail = <T extends ShifuDetailPayload>(
  payload: T | null | undefined,
):
  | (Omit<T, 'can_publish' | 'canPublish'> & { canPublish?: boolean })
  | null => {
  if (!payload) {
    return null;
  }
  const { can_publish, canPublish, ...rest } = payload;
  return {
    ...rest,
    canPublish: canPublish ?? can_publish,
  } as Omit<T, 'can_publish' | 'canPublish'> & { canPublish?: boolean };
};
