export type DeviceOsAnalyticsCategory =
  | 'android'
  | 'chromeos'
  | 'ios'
  | 'linux'
  | 'macos'
  | 'other'
  | 'unknown'
  | 'windows';

const HOST_PLATFORMS = [
  'workbuddy',
  'doubao',
  'lobster',
  'codex',
  'direct',
] as const;
const SKILL_IDS = ['ai-shifu-course-creator'] as const;

type HostPlatform = (typeof HOST_PLATFORMS)[number];
type SkillId = (typeof SKILL_IDS)[number];

export type DeviceAuthorizationAttributionAnalytics = {
  host_platform: HostPlatform | 'unattributed';
  skill_id: SkillId | 'unattributed';
  skill_version: string;
};

type PublicRegistrationAttribution = {
  host_platform?: unknown;
  skill_id?: unknown;
  skill_version?: unknown;
};

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

export const normalizeRegistrationAttributionForAnalytics = (
  value: unknown,
): DeviceAuthorizationAttributionAnalytics => {
  if (!value || typeof value !== 'object') {
    return {
      host_platform: 'unattributed',
      skill_id: 'unattributed',
      skill_version: 'unattributed',
    };
  }

  const attribution = value as PublicRegistrationAttribution;
  const hostPlatform = HOST_PLATFORMS.find(
    candidate => candidate === attribution.host_platform,
  );
  const skillId = SKILL_IDS.find(
    candidate => candidate === attribution.skill_id,
  );
  const skillVersion =
    typeof attribution.skill_version === 'string'
      ? attribution.skill_version.trim()
      : '';
  if (!hostPlatform || !skillId || !skillVersion || skillVersion.length > 32) {
    return {
      host_platform: 'unattributed',
      skill_id: 'unattributed',
      skill_version: 'unattributed',
    };
  }

  return {
    host_platform: hostPlatform,
    skill_id: skillId,
    skill_version: skillVersion,
  };
};
