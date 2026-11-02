export const LIVE_FOLLOW_UP_CAPACITY_SCOPES = [
  'global_credentials',
  'worker_credentials',
  'user_credentials',
  'active_sessions',
  'user_mint_rate',
  'global_mint_rate',
  'legacy_user_credential',
] as const;
export type LiveFollowUpCapacityScope =
  (typeof LIVE_FOLLOW_UP_CAPACITY_SCOPES)[number];

export const normalizeLiveFollowUpCapacityScopes = (
  value: unknown,
): LiveFollowUpCapacityScope[] =>
  Array.isArray(value)
    ? LIVE_FOLLOW_UP_CAPACITY_SCOPES.filter(scope => value.includes(scope))
    : [];
