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

const mockRouter = { replace: mockReplace };

jest.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
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

const mockTrackEvent = jest.fn();

jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
  EVENT_NAMES: {
    DEVICE_AUTH_PROMPT_SHOWN: 'device_auth_prompt_shown',
    DEVICE_AUTH_APPROVED: 'device_auth_approved',
    DEVICE_AUTH_DENIED: 'device_auth_denied',
  },
}));

const pendingDevice = {
  user_code: 'AC4-7HK',
  device_name: 'MacBook-Pro',
  device_os: 'macOS 15',
  client_version: '1.2.6',
  client_ip: '203.0.113.7',
  registration_attribution: {
    host_platform: 'workbuddy',
    skill_id: 'ai-shifu-course-creator',
    skill_version: '1.3.0',
    handoff_id: '123e4567-e89b-12d3-a456-426614174000',
  },
};

const expectedSkillAttribution = {
  host_platform: 'workbuddy',
  skill_id: 'ai-shifu-course-creator',
  skill_version_major: 'v1',
};

// The request layer returns the raw envelope for any path containing '/login',
// so every mock here must use the same shape the page really receives.
const envelope = (data: unknown, code = 0, message = 'success') => ({
  code,
  message,
  data,
});

describe('DeviceAuthorizationPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockTrackEvent.mockReset();
    searchParams = new URLSearchParams('code=AC4-7HK');
    storeState = { isInitialized: true, isLoggedIn: true };
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('shows what is being authorized before asking for a decision', async () => {
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(
      envelope(pendingDevice),
    );

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
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(
      envelope(pendingDevice),
    );

    render(<DeviceAuthorizationPage />);

    await screen.findByText('MacBook-Pro');
    expect(api.deviceAuthApprove).not.toHaveBeenCalled();
  });

  it('approves only when the user confirms', async () => {
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(
      envelope(pendingDevice),
    );
    (api.deviceAuthApprove as jest.Mock).mockResolvedValue(
      envelope({ status: 'approved' }),
    );

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
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(
      envelope(pendingDevice),
    );
    (api.deviceAuthDeny as jest.Mock).mockResolvedValue(
      envelope({ status: 'denied' }),
    );

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

  it('does not render an error envelope as if it were device details', async () => {
    // Reproduces the dev01 failure: an expired session returned
    // {code: 1001, ...} and the page rendered an empty "unknown device" card.
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(
      envelope(null, 4001, 'pairing code is invalid'),
    );

    render(<DeviceAuthorizationPage />);

    expect(
      await screen.findByText('pairing code is invalid'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('module.auth.deviceAuthApprove'),
    ).not.toBeInTheDocument();
  });

  it('does not report success when approval fails with a business error', async () => {
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(
      envelope(pendingDevice),
    );
    (api.deviceAuthApprove as jest.Mock).mockResolvedValue(
      envelope(null, 1029, 'already handled'),
    );

    render(<DeviceAuthorizationPage />);
    fireEvent.click(await screen.findByText('module.auth.deviceAuthApprove'));

    expect(await screen.findByText('already handled')).toBeInTheDocument();
    expect(
      screen.queryByText('module.auth.deviceAuthApprovedTitle'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText('module.auth.deviceAuthApprove'),
    ).toBeInTheDocument();
  });

  it('lets the same user retry after attribution persistence recovers', async () => {
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(
      envelope(pendingDevice),
    );
    (api.deviceAuthApprove as jest.Mock)
      .mockResolvedValueOnce(envelope(null, 3000, 'database unavailable'))
      .mockResolvedValueOnce(envelope({ status: 'approved' }));

    render(<DeviceAuthorizationPage />);
    fireEvent.click(await screen.findByText('module.auth.deviceAuthApprove'));

    expect(await screen.findByText('database unavailable')).toBeInTheDocument();
    fireEvent.click(screen.getByText('module.auth.deviceAuthApprove'));

    await waitFor(() => expect(api.deviceAuthApprove).toHaveBeenCalledTimes(2));
    expect(
      await screen.findByText('module.auth.deviceAuthApprovedTitle'),
    ).toBeInTheDocument();
  });

  it('reports the prompt exposure once, without leaking the pairing code', async () => {
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(
      envelope(pendingDevice),
    );

    const { rerender } = render(<DeviceAuthorizationPage />);
    await screen.findByText('MacBook-Pro');
    rerender(<DeviceAuthorizationPage />);

    const exposures = mockTrackEvent.mock.calls.filter(
      ([name]) => name === 'device_auth_prompt_shown',
    );
    expect(exposures).toHaveLength(1);
    expect(exposures[0][1]).toEqual({
      device_os: 'macos',
      from_link: true,
      ...expectedSkillAttribution,
    });
    // The pairing code is a live credential; it must not reach analytics.
    expect(JSON.stringify(exposures[0][1])).not.toContain('AC4-7HK');
    expect(JSON.stringify(exposures[0][1])).not.toContain('macOS 15');
    expect(JSON.stringify(exposures[0][1])).not.toContain('handoff_id');
    expect(JSON.stringify(exposures[0][1])).not.toContain('426614174000');
  });

  it('keeps the originating link source on a denied outcome', async () => {
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(
      envelope(pendingDevice),
    );
    (api.deviceAuthDeny as jest.Mock).mockResolvedValue(
      envelope({ status: 'denied' }),
    );

    const { rerender } = render(<DeviceAuthorizationPage />);
    await screen.findByText('MacBook-Pro');

    // The terminal event must retain the source of the prompt even if the URL
    // changes while that resolved request remains on screen.
    searchParams = new URLSearchParams('');
    rerender(<DeviceAuthorizationPage />);
    fireEvent.click(screen.getByText('module.auth.deviceAuthDeny'));

    await waitFor(() =>
      expect(mockTrackEvent).toHaveBeenCalledWith('device_auth_denied', {
        device_os: 'macos',
        from_link: true,
        ...expectedSkillAttribution,
      }),
    );
  });

  it('does not report an outcome when the decision failed', async () => {
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(
      envelope(pendingDevice),
    );
    (api.deviceAuthApprove as jest.Mock).mockResolvedValue(
      envelope(null, 1029, 'already handled'),
    );

    render(<DeviceAuthorizationPage />);
    fireEvent.click(await screen.findByText('module.auth.deviceAuthApprove'));

    await screen.findByText('already handled');
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'device_auth_approved',
      expect.anything(),
    );
  });

  it('sends the user back to login when the session expired', async () => {
    const authError = Object.assign(new Error('User Not Found'), {
      code: 1001,
    });
    (api.deviceAuthPending as jest.Mock).mockRejectedValue(authError);

    render(<DeviceAuthorizationPage />);

    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith(
        `/login?redirect=${encodeURIComponent('/login/device?code=AC4-7HK')}`,
      ),
    );
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
    let resolveLinkedReload!: (value: ReturnType<typeof envelope>) => void;
    const linkedReload = new Promise<ReturnType<typeof envelope>>(resolve => {
      resolveLinkedReload = resolve;
    });
    (api.deviceAuthPending as jest.Mock)
      .mockResolvedValueOnce(envelope(pendingDevice))
      .mockReturnValueOnce(linkedReload);
    (api.deviceAuthApprove as jest.Mock).mockResolvedValue(
      envelope({ status: 'approved' }),
    );

    const { rerender } = render(<DeviceAuthorizationPage />);

    fireEvent.change(screen.getByLabelText('module.auth.deviceAuthCodeLabel'), {
      target: { value: 'ac4-7hk' },
    });
    fireEvent.click(screen.getByText('module.auth.deviceAuthContinue'));

    await waitFor(() =>
      expect(api.deviceAuthPending).toHaveBeenCalledWith({
        user_code: 'ac4-7hk',
      }),
    );
    expect(mockTrackEvent).toHaveBeenCalledWith('device_auth_prompt_shown', {
      device_os: 'macos',
      from_link: false,
      ...expectedSkillAttribution,
    });

    // Re-resolving the same code from a link must not change the source of the
    // already-counted exposure used by the terminal outcome.
    searchParams = new URLSearchParams('code=AC4-7HK');
    rerender(<DeviceAuthorizationPage />);
    await waitFor(() =>
      expect(api.deviceAuthPending).toHaveBeenLastCalledWith({
        user_code: 'AC4-7HK',
      }),
    );
    expect(
      await screen.findByText('module.auth.deviceAuthLoading'),
    ).toBeInTheDocument();
    resolveLinkedReload(envelope(pendingDevice));
    await screen.findByText('MacBook-Pro');
    const exposures = mockTrackEvent.mock.calls.filter(
      ([name]) => name === 'device_auth_prompt_shown',
    );
    expect(exposures).toHaveLength(1);
    fireEvent.click(await screen.findByText('module.auth.deviceAuthApprove'));

    await waitFor(() =>
      expect(mockTrackEvent).toHaveBeenCalledWith('device_auth_approved', {
        device_os: 'macos',
        from_link: false,
        ...expectedSkillAttribution,
      }),
    );
    const approvedPayload = mockTrackEvent.mock.calls.find(
      ([name]) => name === 'device_auth_approved',
    )?.[1];
    expect(JSON.stringify(approvedPayload)).not.toContain('AC4-7HK');
    expect(JSON.stringify(approvedPayload)).not.toContain('macOS 15');
    expect(JSON.stringify(approvedPayload)).not.toContain('handoff_id');
  });

  it('groups ordinary device authorization as unattributed', async () => {
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(
      envelope({ ...pendingDevice, registration_attribution: undefined }),
    );

    render(<DeviceAuthorizationPage />);

    await screen.findByText('MacBook-Pro');
    expect(mockTrackEvent).toHaveBeenCalledWith('device_auth_prompt_shown', {
      device_os: 'macos',
      from_link: true,
      host_platform: 'unattributed',
      skill_id: 'unattributed',
      skill_version_major: 'unattributed',
    });
  });

  it('never sends a caller-owned Skill version to analytics', async () => {
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(
      envelope({
        ...pendingDevice,
        registration_attribution: {
          ...pendingDevice.registration_attribution,
          skill_version: 'person@example.test',
        },
      }),
    );

    render(<DeviceAuthorizationPage />);

    await screen.findByText('MacBook-Pro');
    const exposure = mockTrackEvent.mock.calls.find(
      ([name]) => name === 'device_auth_prompt_shown',
    )?.[1];
    expect(exposure).toEqual({
      device_os: 'macos',
      from_link: true,
      host_platform: 'workbuddy',
      skill_id: 'ai-shifu-course-creator',
      skill_version_major: 'unknown',
    });
    expect(JSON.stringify(exposure)).not.toContain('person@example.test');
  });

  it('keeps approval working when tracking throws', async () => {
    mockTrackEvent.mockImplementation(() => {
      throw new Error('analytics unavailable');
    });
    (api.deviceAuthPending as jest.Mock).mockResolvedValue(
      envelope(pendingDevice),
    );
    (api.deviceAuthApprove as jest.Mock).mockResolvedValue(
      envelope({ status: 'approved' }),
    );

    render(<DeviceAuthorizationPage />);
    fireEvent.click(await screen.findByText('module.auth.deviceAuthApprove'));

    expect(
      await screen.findByText('module.auth.deviceAuthApprovedTitle'),
    ).toBeInTheDocument();
  });

  it('preserves a manually entered code when authentication is required', async () => {
    searchParams = new URLSearchParams('');
    const authError = Object.assign(new Error('User Not Found'), {
      code: 1001,
    });
    (api.deviceAuthPending as jest.Mock).mockRejectedValue(authError);

    render(<DeviceAuthorizationPage />);
    fireEvent.change(screen.getByLabelText('module.auth.deviceAuthCodeLabel'), {
      target: { value: 'ac4-7hk' },
    });
    fireEvent.click(screen.getByText('module.auth.deviceAuthContinue'));

    await waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith(
        `/login?redirect=${encodeURIComponent('/login/device?code=ac4-7hk')}`,
      ),
    );
  });
});
