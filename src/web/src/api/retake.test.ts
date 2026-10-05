import { getRetakePolicy, getRetakeStatus, setRetakePolicy } from './retake';

jest.mock('@/lib/envUtils', () => ({ getStringEnv: () => '' }));
jest.mock('@/store', () => ({
  useUserStore: { getState: () => ({ getToken: () => '', logout: jest.fn() }) },
}));
jest.mock('@/config/environment', () => ({
  getDynamicApiBaseUrl: async () => 'https://example.test',
  getCachedDynamicApiBaseUrl: () => 'https://example.test',
}));
jest.mock('@/hooks/useToast', () => ({
  toast: jest.fn(),
  toastOnce: jest.fn(),
}));

const originalFetch = global.fetch;
afterEach(() => {
  global.fetch = originalFetch;
});

function respond(data: object, code = 0) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => ({ code, data, message: code ? 'unavailable' : 'ok' }),
  });
}

it.each([true, false])(
  'reads allowance through the real request envelope, available=%s',
  async available => {
    const status = {
      available,
      limit: 2,
      used: 1,
      reserved: 0,
      remaining: 1,
      allowed: true,
      in_progress: false,
    };
    respond(status);
    await expect(getRetakeStatus('course', 'lesson')).resolves.toEqual(status);
  },
);

it('reads and saves teacher policy through the real request envelope', async () => {
  const policy = { available: true, configured: true, limit: 3 };
  respond(policy);
  await expect(getRetakePolicy('course')).resolves.toEqual(policy);
  await expect(setRetakePolicy('course', 3)).resolves.toEqual(policy);
  expect(global.fetch).toHaveBeenLastCalledWith(
    'https://example.test/api/learn/shifu/course/retake-policy',
    expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ limit: 3 }),
    }),
  );
});

it('still rejects real business errors instead of treating them as unlimited', async () => {
  respond({}, 4026);
  await expect(getRetakeStatus('course', 'lesson')).rejects.toMatchObject({
    code: 4026,
  });
});
