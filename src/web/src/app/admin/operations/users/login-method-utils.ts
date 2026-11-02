const SUPPORTED_LOGIN_METHODS = new Set([
  'phone',
  'email',
  'google',
  'wechat',
  'unknown',
]);

export const normalizeLoginMethodLabelKey = (method: string): string => {
  const normalized = method.trim().toLowerCase();
  if (!normalized) {
    return 'unknown';
  }
  return SUPPORTED_LOGIN_METHODS.has(normalized) ? normalized : 'unknown';
};
