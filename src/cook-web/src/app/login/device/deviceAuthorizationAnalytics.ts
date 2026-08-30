export type DeviceOsAnalyticsCategory =
  | 'android'
  | 'chromeos'
  | 'ios'
  | 'linux'
  | 'macos'
  | 'other'
  | 'unknown'
  | 'windows';

const DEVICE_OS_PATTERNS: Array<[DeviceOsAnalyticsCategory, RegExp]> = [
  ['android', /\bandroid\b/],
  ['ios', /\b(?:ios|ipados|iphone|ipad)\b/],
  ['macos', /\b(?:macos|mac os|os x|darwin)\b/],
  ['windows', /\b(?:windows|win32|win64)\b/],
  ['chromeos', /\b(?:chromeos|chrome os|cros)\b/],
  ['linux', /\b(?:linux|ubuntu|debian|fedora|centos|red hat|arch)\b/],
];

export const normalizeDeviceOsForAnalytics = (
  value: unknown,
): DeviceOsAnalyticsCategory => {
  if (typeof value !== 'string' || !value.trim()) {
    return 'unknown';
  }

  const normalized = value.trim().toLowerCase().replace(/[_-]+/g, ' ');
  return (
    DEVICE_OS_PATTERNS.find(([, pattern]) => pattern.test(normalized))?.[0] ??
    'other'
  );
};
