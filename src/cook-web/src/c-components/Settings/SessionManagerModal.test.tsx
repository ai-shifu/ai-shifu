import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import apiService from '@/api';

import SessionManagerModal from './SessionManagerModal';

const mockToast = jest.fn();
const mockTrackEvent = jest.fn();

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    listSessions: jest.fn(),
    revokeSession: jest.fn(),
    revokeOtherSessions: jest.fn(),
  },
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
  EVENT_NAMES: {
    SESSION_REVOKED: 'session_revoked',
    SESSION_REVOKED_OTHERS: 'session_revoked_others',
  },
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en-US' },
  }),
}));

jest.mock('./SettingBaseModal', () => {
  const MockModal = ({
    open,
    children,
  }: React.PropsWithChildren<{ open: boolean }>) =>
    open ? <div>{children}</div> : null;
  MockModal.displayName = 'MockSettingBaseModal';
  return { __esModule: true, default: MockModal };
});

const current = {
  session_bid: 'bid-current',
  source: 'web',
  device_name: 'Chrome',
  device_os: 'macOS',
  created_ip: '203.0.113.1',
  created_at: '2026-08-30T10:00:00Z',
  last_seen_at: '2026-08-30T12:00:00Z',
  expires_at: '2026-09-29T12:00:00Z',
  is_current: true,
};

const cliSession = {
  ...current,
  session_bid: 'bid-cli',
  source: 'cli',
  device_name: 'MacBook-Pro',
  device_os: 'macOS 15',
  is_current: false,
};

describe('SessionManagerModal', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (apiService.listSessions as jest.Mock).mockResolvedValue([
      current,
      cliSession,
    ]);
  });

  it('lists the sessions and marks the current one', async () => {
    render(
      <SessionManagerModal
        open
        onClose={jest.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByText(/Chrome/)).toBeInTheDocument());
    expect(screen.getByText(/MacBook-Pro/)).toBeInTheDocument();
    expect(
      screen.getByText('module.settings.sessionsCurrent'),
    ).toBeInTheDocument();
  });

  it('offers no way to end the session you are using', async () => {
    render(
      <SessionManagerModal
        open
        onClose={jest.fn()}
      />,
    );

    await screen.findByText(/Chrome/);
    // One revoke button for the CLI session, none for the current one.
    expect(screen.getAllByText('module.settings.sessionsRevoke')).toHaveLength(
      1,
    );
  });

  it('ends one session and reloads the list', async () => {
    (apiService.revokeSession as jest.Mock).mockResolvedValue({ revoked: 1 });

    render(
      <SessionManagerModal
        open
        onClose={jest.fn()}
      />,
    );

    await waitFor(() =>
      expect(
        screen.getByText('module.settings.sessionsRevoke'),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText('module.settings.sessionsRevoke'));

    await waitFor(() =>
      expect(apiService.revokeSession).toHaveBeenCalledWith({
        session_bid: 'bid-cli',
      }),
    );
    expect(apiService.listSessions).toHaveBeenCalledTimes(2);
    expect(mockTrackEvent).toHaveBeenCalledWith('session_revoked', {
      source: 'cli',
    });
  });

  it('ends every other session on request', async () => {
    (apiService.revokeOtherSessions as jest.Mock).mockResolvedValue({
      revoked: 1,
    });

    render(
      <SessionManagerModal
        open
        onClose={jest.fn()}
      />,
    );

    await waitFor(() =>
      expect(
        screen.getByText('module.settings.sessionsRevokeOthers'),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText('module.settings.sessionsRevokeOthers'));

    await waitFor(() =>
      expect(apiService.revokeOtherSessions).toHaveBeenCalled(),
    );
    expect(mockTrackEvent).toHaveBeenCalledWith('session_revoked_others', {});
  });

  it('reports no outcome when a revoke fails', async () => {
    (apiService.revokeSession as jest.Mock).mockRejectedValue(
      new Error('server said no'),
    );

    render(
      <SessionManagerModal
        open
        onClose={jest.fn()}
      />,
    );
    await waitFor(() =>
      expect(
        screen.getByText('module.settings.sessionsRevoke'),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText('module.settings.sessionsRevoke'));

    await waitFor(() => expect(mockToast).toHaveBeenCalled());
    expect(mockTrackEvent).not.toHaveBeenCalledWith(
      'session_revoked',
      expect.anything(),
    );
  });

  it('keeps session identifiers out of analytics', async () => {
    (apiService.revokeSession as jest.Mock).mockResolvedValue({ revoked: 1 });

    render(
      <SessionManagerModal
        open
        onClose={jest.fn()}
      />,
    );
    await waitFor(() =>
      expect(
        screen.getByText('module.settings.sessionsRevoke'),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText('module.settings.sessionsRevoke'));

    await waitFor(() => expect(mockTrackEvent).toHaveBeenCalled());
    // A session id names a live credential's row; it must not reach analytics.
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain('bid-cli');
  });

  it('reports a load failure instead of showing an empty list', async () => {
    (apiService.listSessions as jest.Mock).mockRejectedValue(
      new Error('network down'),
    );

    render(
      <SessionManagerModal
        open
        onClose={jest.fn()}
      />,
    );

    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'network down' }),
      ),
    );
  });

  it('loads exactly once per open', async () => {
    // Regression guard: callbacks here must not depend on `t`, `toast` or
    // `trackEvent`, whose hooks return a new identity on every render. An
    // effect depending on such a callback re-runs without end, and the list
    // flickers back to its spinner each time.
    render(
      <SessionManagerModal
        open
        onClose={jest.fn()}
      />,
    );

    await waitFor(() => expect(apiService.listSessions).toHaveBeenCalled());
    await new Promise(resolve => setTimeout(resolve, 60));

    expect(apiService.listSessions).toHaveBeenCalledTimes(1);
  });

  it('shows the loading state, not the old list, when reopened', async () => {
    // Asserting while closed would pass no matter what, since the dialog
    // renders nothing then; the check happens after it reopens, before the
    // new response lands. What this pins down is that reopening starts from
    // the loading state rather than the previous account's rows.
    const { rerender } = render(
      <SessionManagerModal
        open
        onClose={jest.fn()}
      />,
    );
    await waitFor(() => expect(screen.getByText(/Chrome/)).toBeInTheDocument());

    rerender(
      <SessionManagerModal
        open={false}
        onClose={jest.fn()}
      />,
    );
    (apiService.listSessions as jest.Mock).mockReturnValue(
      new Promise(() => {}),
    );
    rerender(
      <SessionManagerModal
        open
        onClose={jest.fn()}
      />,
    );

    expect(screen.queryByText(/Chrome/)).not.toBeInTheDocument();
  });

  it('ignores a response that arrives after it closed', async () => {
    let release: (value: unknown) => void = () => {};
    (apiService.listSessions as jest.Mock).mockReturnValueOnce(
      new Promise(resolve => {
        release = resolve;
      }),
    );

    const { rerender } = render(
      <SessionManagerModal
        open
        onClose={jest.fn()}
      />,
    );
    rerender(
      <SessionManagerModal
        open={false}
        onClose={jest.fn()}
      />,
    );

    // The first request only now comes back, after the dialog was dismissed.
    release([current, cliSession]);
    await new Promise(resolve => setTimeout(resolve, 20));

    (apiService.listSessions as jest.Mock).mockReturnValue(
      new Promise(() => {}),
    );
    rerender(
      <SessionManagerModal
        open
        onClose={jest.fn()}
      />,
    );

    expect(screen.queryByText(/Chrome/)).not.toBeInTheDocument();
  });

  it('does not load anything while closed', () => {
    render(
      <SessionManagerModal
        open={false}
        onClose={jest.fn()}
      />,
    );

    expect(apiService.listSessions).not.toHaveBeenCalled();
  });
});
