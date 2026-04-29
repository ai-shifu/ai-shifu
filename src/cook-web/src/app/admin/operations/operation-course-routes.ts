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

export const buildAdminOperationsOrdersUrl = (
  shifuBid: string,
): string | null => {
  const normalizedShifuBid = shifuBid.trim();
  if (!normalizedShifuBid) {
    return null;
  }
  const params = new URLSearchParams({
    shifu_bid: normalizedShifuBid,
  });
  return `/admin/operations/orders?${params.toString()}`;
};
