import api from '@/api';
import { gen } from './api';
import http from './request';

jest.mock('./request', () => ({
  __esModule: true,
  default: {
    delete: jest.fn(),
    get: jest.fn(),
    patch: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
  },
}));

const mockHttp = http as jest.Mocked<typeof http>;

describe('api generator', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('posts current-password changes through the registered API client', async () => {
    const payload = {
      old_password: 'current-password-value',
      new_password: 'replacement-password-value',
    };

    await api.changePassword(payload);

    expect(mockHttp.post).toHaveBeenCalledTimes(1);
    expect(mockHttp.post).toHaveBeenCalledWith(
      '/api/user/change_password',
      payload,
      {},
    );
  });

  test('serializes DELETE params as query string', async () => {
    await gen('DELETE /admin/billing/customization-draft')({
      creator_bid: 'creator-1',
    });

    expect(mockHttp.delete).toHaveBeenCalledWith(
      '/api/admin/billing/customization-draft?creator_bid=creator-1',
      {},
    );
  });

  test('keeps DELETE path params in the path and serializes remaining params', async () => {
    await gen('DELETE /billing/customization/domains/{domain_binding_bid}')({
      domain_binding_bid: 'domain-1',
      force: '1',
    });

    expect(mockHttp.delete).toHaveBeenCalledWith(
      '/api/billing/customization/domains/domain-1?force=1',
      {},
    );
  });
});
