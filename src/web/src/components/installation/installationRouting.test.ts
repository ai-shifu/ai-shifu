import {
  getAdminEntryPath,
  getLocalAdminRedirect,
  isSecureInstallationOrigin,
} from './installationRouting';

it.each([
  ['https:', 'app.example.com', true],
  ['http:', 'localhost', true],
  ['http:', 'LOCALHOST.', true],
  ['http:', '127.0.0.0', true],
  ['http:', '127.0.0.1', true],
  ['http:', '127.0.0.2', true],
  ['http:', '127.255.255.255', true],
  ['http:', '127.0.0.2.', true],
  ['http:', '[::1]', true],
  ['http:', '::1', true],
  ['http:', '[0:0:0:0:0:0:0:1]', true],
  ['http:', '0:0:0:0:0:0:0:1', true],
  ['http:', '[::0001]', true],
  ['http:', '[::ffff:127.0.0.0]', true],
  ['http:', '[::ffff:127.0.0.2]', true],
  ['http:', '[::ffff:7f00:1]', true],
  ['http:', '[::ffff:7fff:ffff]', true],
  ['http:', 'app.example.com', false],
  ['http:', 'localhost.example.com', false],
  ['http:', 'sub.localhost', false],
  ['http:', '126.255.255.255', false],
  ['http:', '128.0.0.1', false],
  ['http:', '192.168.1.2', false],
  ['http:', '127.0.0.256', false],
  ['http:', '127.256.0.1', false],
  ['http:', '127.00.0.1', false],
  ['http:', '127.0.1', false],
  ['http:', '127.0.0.1.example.com', false],
  ['http:', '127.0.0.1@evil.example', false],
  ['http:', '[::2]', false],
  ['http:', '[::ffff:126.0.0.1]', false],
  ['http:', '[::ffff:128.0.0.1]', false],
  ['http:', '[::ffff:192.168.1.2]', false],
  ['http:', '[::127.0.0.1]', false],
  ['http:', '[::1%lo0]', false],
  ['http:', '[::1', false],
  ['http:', '[::1].', false],
  ['file:', 'localhost', false],
])(
  'checks safe browser transport for %s %s',
  (protocol, hostname, expected) => {
    expect(isSecureInstallationOrigin({ protocol, hostname })).toBe(expected);
  },
);

it.each([
  'http://127.0.0.2:8080',
  'http://127.255.255.254:8080',
  'http://[0:0:0:0:0:0:0:1]:8080',
  'http://[::ffff:127.0.0.2]:8080',
])('accepts the browser hostname for loopback origin %s', origin => {
  expect(isSecureInstallationOrigin(new URL(origin))).toBe(true);
});

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
