import { normalizeDeviceOsForAnalytics } from './deviceAuthorizationAnalytics';

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
