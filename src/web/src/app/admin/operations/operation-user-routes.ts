export const buildAdminOperationsUserDetailUrl = (
  userBid: string,
): string | null => {
  const normalizedUserBid = userBid.trim();
  if (!normalizedUserBid) {
    return null;
  }
  return `/admin/operations/users/${encodeURIComponent(normalizedUserBid)}`;
};
