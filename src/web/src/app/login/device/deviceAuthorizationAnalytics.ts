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
  skill_version_major: `v${number}` | 'unknown' | 'unattributed';
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
      skill_version_major: 'unattributed',
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
  if (!hostPlatform || !skillId) {
    return {
      host_platform: 'unattributed',
      skill_id: 'unattributed',
      skill_version_major: 'unattributed',
    };
  }

  // The device-authorization endpoint is public. Never send its caller-owned
  // version string to analytics: retain only one bounded semantic-version
  // major bucket, and collapse everything else to a fixed value.
  const semanticVersion =
    /^v?([0-9])\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/.exec(
      skillVersion,
    );

  return {
    host_platform: hostPlatform,
    skill_id: skillId,
    skill_version_major: semanticVersion
      ? (`v${semanticVersion[1]}` as `v${number}`)
      : 'unknown',
  };
};
