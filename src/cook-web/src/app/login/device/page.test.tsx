import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';

import DeviceAuthorizationPage from './page';

const mockReplace = jest.fn();
let searchParams = new URLSearchParams('code=AC4-7HK');
let storeState = {
  isInitialized: true,
  isLoggedIn: true,
};

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: mockReplace,
  }),
  useSearchParams: () => searchParams,
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    deviceAuthPending: jest.fn(),
    deviceAuthApprove: jest.fn(),
    deviceAuthDeny: jest.fn(),
  },
}));

jest.mock('@/store', () => ({
  __esModule: true,
  useUserStore: (selector: (state: typeof storeState) => unknown) =>
    selector(storeState),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const pendingDevice = {
  user_code: 'AC4-7HK',
  device_name: 'MacBook-Pro',
  device_os: 'macOS 15',
  client_version: '1.2.6',
  client_ip: '203.0.113.7',
};

describe('DeviceAuthorizationPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    searchParams = new URLSearchParams('code=AC4-7HK');
    storeState = { isInitialized: true, isLoggedIn: true };
  });

  it('shows what is being authorized before asking for a decision', async () => {
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(pendingDevice);

    render(<DeviceAuthorizationPage />);

    await waitFor(() =>
      expect(api.deviceAuthPending).toHaveBeenCalledWith({
        user_code: 'AC4-7HK',
      }),
    );
    expect(await screen.findByText('MacBook-Pro')).toBeInTheDocument();
    expect(screen.getByText('macOS 15')).toBeInTheDocument();
    expect(screen.getByText('203.0.113.7')).toBeInTheDocument();
    // The warning must be visible before the user can approve anything.
    expect(
      screen.getByText('module.auth.deviceAuthWarning'),
    ).toBeInTheDocument();
  });

  it('does not authorize anything without an explicit click', async () => {
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(pendingDevice);

    render(<DeviceAuthorizationPage />);

    await screen.findByText('MacBook-Pro');
    expect(api.deviceAuthApprove).not.toHaveBeenCalled();
  });

  it('approves only when the user confirms', async () => {
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(pendingDevice);
    (api.deviceAuthApprove as jest.Mock).mockResolvedValue({
      status: 'approved',
    });

    render(<DeviceAuthorizationPage />);

    fireEvent.click(await screen.findByText('module.auth.deviceAuthApprove'));

    await waitFor(() =>
      expect(api.deviceAuthApprove).toHaveBeenCalledWith({
        user_code: 'AC4-7HK',
      }),
    );
    expect(
      await screen.findByText('module.auth.deviceAuthApprovedTitle'),
    ).toBeInTheDocument();
  });

  it('rejects the request when the user denies it', async () => {
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(pendingDevice);
    (api.deviceAuthDeny as jest.Mock).mockResolvedValue({ status: 'denied' });

    render(<DeviceAuthorizationPage />);

    fireEvent.click(await screen.findByText('module.auth.deviceAuthDeny'));

    await waitFor(() =>
      expect(api.deviceAuthDeny).toHaveBeenCalledWith({ user_code: 'AC4-7HK' }),
    );
    expect(
      await screen.findByText('module.auth.deviceAuthDeniedTitle'),
    ).toBeInTheDocument();
  });

  it('surfaces an expired pairing code instead of a blank page', async () => {
    (api.deviceAuthPending as jest.Mock).mockRejectedValue(
      new Error('pairing code expired'),
    );

    render(<DeviceAuthorizationPage />);

    expect(await screen.findByText('pairing code expired')).toBeInTheDocument();
  });

  it('sends a signed-out visitor through login and back again', async () => {
    storeState = { isInitialized: true, isLoggedIn: false };

    render(<DeviceAuthorizationPage />);

    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith(
        `/login?redirect=${encodeURIComponent('/login/device?code=AC4-7HK')}`,
      ),
    );
    expect(api.deviceAuthPending).not.toHaveBeenCalled();
  });

  it('lets the user type the pairing code when the link has none', async () => {
    searchParams = new URLSearchParams('');
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(pendingDevice);

    render(<DeviceAuthorizationPage />);

    fireEvent.change(screen.getByLabelText('module.auth.deviceAuthCodeLabel'), {
      target: { value: 'ac4-7hk' },
    });
    fireEvent.click(screen.getByText('module.auth.deviceAuthContinue'));

    await waitFor(() =>
      expect(api.deviceAuthPending).toHaveBeenCalledWith({
        user_code: 'ac4-7hk',
      }),
    );
  });
});
