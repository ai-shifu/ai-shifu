const SUCCESS_ORDER_STATUS = '502';

export const buildAdminOrdersUrl = (shifuBid: string): string | null => {
  const normalizedShifuBid = shifuBid.trim();
  if (!normalizedShifuBid) {
    return null;
  }
  const params = new URLSearchParams({
    shifu_bid: normalizedShifuBid,
    status: SUCCESS_ORDER_STATUS,
  });
  return `/admin/orders?${params.toString()}`;
};
