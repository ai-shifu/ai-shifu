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

export const buildAdminDashboardCourseDetailUrl = (
  shifuBid: string,
): string | null => {
  const normalizedShifuBid = shifuBid.trim();
  if (!normalizedShifuBid) {
    return null;
  }
  return `/admin/dashboard/${encodeURIComponent(normalizedShifuBid)}`;
};

export const buildAdminDashboardCourseFollowUpsUrl = (
  shifuBid: string,
  options?: {
    userBid?: string;
    keyword?: string;
  },
): string | null => {
  const normalizedShifuBid = shifuBid.trim();
  if (!normalizedShifuBid) {
    return null;
  }
  const params = new URLSearchParams();
  const normalizedUserBid = options?.userBid?.trim() || '';
  const normalizedKeyword = options?.keyword?.trim() || '';
  if (normalizedUserBid) {
    params.set('user_bid', normalizedUserBid);
  }
  if (normalizedKeyword) {
    params.set('keyword', normalizedKeyword);
  }
  const basePath = `/admin/dashboard/${encodeURIComponent(normalizedShifuBid)}/follow-ups`;
  const query = params.toString();
  return query ? `${basePath}?${query}` : basePath;
};

export const buildAdminDashboardCourseRatingsUrl = (
  shifuBid: string,
): string | null => {
  const normalizedShifuBid = shifuBid.trim();
  if (!normalizedShifuBid) {
    return null;
  }
  return `/admin/dashboard/${encodeURIComponent(normalizedShifuBid)}/ratings`;
};
