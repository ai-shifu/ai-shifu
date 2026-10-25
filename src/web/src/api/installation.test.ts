import request from '@/lib/request';
import {
  getInstallationStatus,
  initializeAdministrator,
  loginLocalAdministrator,
} from './installation';

jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

beforeEach(() => jest.clearAllMocks());

it('reads status through the shared business-response transport', async () => {
  const status = { setup_required: true, local_admin_login_enabled: false };
  (request.get as jest.Mock).mockResolvedValue(status);
  await expect(getInstallationStatus()).resolves.toEqual(status);
  expect(request.get).toHaveBeenCalledWith('/api/installation/status', {
    skipErrorToast: true,
    cache: 'no-store',
  });
});

it.each([
  null,
  {},
  { setup_required: 'true', local_admin_login_enabled: false },
])(
  'rejects malformed status instead of sending users to a guessed login flow',
  async value => {
    (request.get as jest.Mock).mockResolvedValue(value);
    await expect(getInstallationStatus()).rejects.toThrow(
      'Invalid installation status response',
    );
  },
);

it('keeps the setup claim and password in the POST body', async () => {
  const payload = {
    setup_token: 'single-use-test-claim',
    username: 'owner',
    password: 'LongPassword1',
    language: 'en-US',
  };
  await initializeAdministrator(payload);
  expect(request.post).toHaveBeenCalledWith(
    '/api/installation/initialize',
    payload,
    { skipErrorToast: true },
  );
});

it('uses the independent administrator login endpoint', async () => {
  const payload = {
    username: 'owner',
    password: 'LongPassword1',
    language: 'en-US',
  };
  await loginLocalAdministrator(payload);
  expect(request.post).toHaveBeenCalledWith(
    '/api/installation/login',
    payload,
    { skipErrorToast: true },
  );
});
