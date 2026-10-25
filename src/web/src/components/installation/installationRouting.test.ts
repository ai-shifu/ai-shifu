import {
  getAdminEntryPath,
  getLocalAdminRedirect,
  isSecureInstallationOrigin,
} from './installationRouting';

it.each([
  ['https:', 'app.example.com', true],
  ['http:', 'localhost', true],
  ['http:', '127.0.0.1', true],
  ['http:', '[::1]', true],
  ['http:', 'app.example.com', false],
  ['http:', 'localhost.example.com', false],
  ['file:', 'localhost', false],
])(
  'checks safe browser transport for %s %s',
  (protocol, hostname, expected) => {
    expect(isSecureInstallationOrigin({ protocol, hostname })).toBe(expected);
  },
);

it('routes pending, local and legacy installations to their own entry', () => {
  expect(
    getAdminEntryPath(
      { setup_required: true, local_admin_login_enabled: false },
      '/admin/billing?tab=details',
    ),
  ).toBe('/setup');
  expect(
    getAdminEntryPath(
      { setup_required: false, local_admin_login_enabled: true },
      '/admin/billing?tab=details',
    ),
  ).toBe('/admin-login?redirect=%2Fadmin%2Fbilling%3Ftab%3Ddetails');
  expect(
    getAdminEntryPath(
      { setup_required: false, local_admin_login_enabled: false },
      '/admin',
    ),
  ).toBe('/login?redirect=%2Fadmin');
});

it.each([
  'https://evil.example/',
  '//evil.example/admin',
  '/administrator',
  '/c/one',
])('rejects non-admin return targets: %s', redirect => {
  expect(
    getLocalAdminRedirect('?redirect=' + encodeURIComponent(redirect)),
  ).toBe('/admin');
});

it('preserves an admin return path and query', () => {
  expect(
    getLocalAdminRedirect('?redirect=%2Fadmin%2Fbilling%3Ftab%3Ddetails'),
  ).toBe('/admin/billing?tab=details');
});
