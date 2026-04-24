export const buildAdminOperationsCourseDetailUrl = (
  shifuBid: string,
): string | null => {
  const normalizedShifuBid = shifuBid.trim();
  if (!normalizedShifuBid) {
    return null;
  }
  return `/admin/operations/${encodeURIComponent(normalizedShifuBid)}`;
};

export const buildAdminOperationsCourseFollowUpsUrl = (
  shifuBid: string,
): string | null => {
  const normalizedShifuBid = shifuBid.trim();
  if (!normalizedShifuBid) {
    return null;
  }
  return `/admin/operations/${encodeURIComponent(normalizedShifuBid)}/follow-ups`;
};
