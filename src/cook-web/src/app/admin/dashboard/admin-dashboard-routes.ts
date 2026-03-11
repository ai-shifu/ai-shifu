export const buildAdminOrdersUrl = (shifuBid: string): string | null => {
  const normalizedShifuBid = shifuBid.trim();
  if (!normalizedShifuBid) {
    return null;
  }
  const params = new URLSearchParams({
    shifu_bid: normalizedShifuBid,
  });
  return `/admin/orders?${params.toString()}`;
};
