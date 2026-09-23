import {
  normalizeDeviceOsForAnalytics,
  normalizeRegistrationAttributionForAnalytics,
} from './deviceAuthorizationAnalytics';

describe('normalizeDeviceOsForAnalytics', () => {
  test.each([
    ['macOS 15', 'macos'],
    ['Darwin 24', 'macos'],
    ['Windows 11', 'windows'],
    ['win32', 'windows'],
    ['Ubuntu 24.04', 'linux'],
    ['Chrome OS', 'chromeos'],
    ['Android 15', 'android'],
    ['iPadOS 18', 'ios'],
    ['', 'unknown'],
    [undefined, 'unknown'],
    ['person@example.test custom workstation', 'other'],
  ])('maps %p to the bounded category %s', (value, expected) => {
    expect(normalizeDeviceOsForAnalytics(value)).toBe(expected);
  });
});

describe('normalizeRegistrationAttributionForAnalytics', () => {
  it('keeps only the supported aggregate dimensions', () => {
    expect(
      normalizeRegistrationAttributionForAnalytics({
        host_platform: 'workbuddy',
        skill_id: 'ai-shifu-course-creator',
        skill_version: '1.3.0',
        handoff_id: '123e4567-e89b-12d3-a456-426614174000',
        user_code: 'AC4-7HK',
      }),
    ).toEqual({
      host_platform: 'workbuddy',
      skill_id: 'ai-shifu-course-creator',
      skill_version: '1.3.0',
    });
  });

  test.each([
    undefined,
    null,
    {},
    {
      host_platform: 'custom-platform',
      skill_id: 'ai-shifu-course-creator',
      skill_version: '1.3.0',
    },
    {
      host_platform: 'doubao',
      skill_id: 'unknown-skill',
      skill_version: '1.3.0',
    },
    {
      host_platform: 'doubao',
      skill_id: 'ai-shifu-course-creator',
      skill_version: '',
    },
  ])('uses a stable unattributed group for invalid input %#', value => {
    expect(normalizeRegistrationAttributionForAnalytics(value)).toEqual({
      host_platform: 'unattributed',
      skill_id: 'unattributed',
      skill_version: 'unattributed',
    });
  });
});
