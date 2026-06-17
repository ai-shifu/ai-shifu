import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import { ReferralInviteLanding } from './ReferralInviteLanding';

const mockPush = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

jest.mock('next/image', () => ({
  __esModule: true,
  default: ({
    priority,
    alt = '',
    ...props
  }: React.ImgHTMLAttributes<HTMLImageElement> & { priority?: boolean }) => {
    void priority;
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        alt={alt}
        {...props}
      />
    );
  },
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getReferralInvitePreview: jest.fn(),
    recordReferralInviteEvent: jest.fn(),
  },
}));

const mockEnvState: { officialSiteUrl: string } = {
  officialSiteUrl: 'https://official.example.com',
};

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (
    selector: ((state: typeof mockEnvState) => unknown) | undefined,
  ) => (selector ? selector(mockEnvState) : mockEnvState),
}));

jest.mock('@/components/contact/ContactSideRail', () => ({
  ContactSideRail: () => <div data-testid='contact-side-rail' />,
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      values
        ? `module.referral.${key}:${JSON.stringify(values)}`
        : `module.referral.${key}`,
  }),
}));

describe('ReferralInviteLanding', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    window.localStorage.clear();
    mockEnvState.officialSiteUrl = 'https://official.example.com';
    (api.getReferralInvitePreview as jest.Mock).mockResolvedValue({
      recognized: true,
      invite_code: 'AB12CD34',
      inviter_mobile_masked: '155****0064',
    });
    (api.recordReferralInviteEvent as jest.Mock).mockResolvedValue({
      success: true,
      session_id: 'session-1',
      recognized: true,
    });
  });

  test('records link events and renders invite preview for invite-code route', async () => {
    render(<ReferralInviteLanding initialInviteCode='ab12cd34' />);

    await waitFor(() =>
      expect(api.getReferralInvitePreview).toHaveBeenCalledWith(
        { invite_code: 'AB12CD34' },
        { skipErrorToast: true },
      ),
    );
    await waitFor(() =>
      expect(api.recordReferralInviteEvent).toHaveBeenCalledWith(
        expect.objectContaining({
          event_type: 'invite_link_clicked',
          invite_code: 'AB12CD34',
          entry_source: 'invite_link',
        }),
        { skipErrorToast: true },
      ),
    );
    expect(api.recordReferralInviteEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        event_type: 'registration_page_viewed',
        invite_code: 'AB12CD34',
        entry_source: 'invite_link',
      }),
      { skipErrorToast: true },
    );
    expect(
      screen.getByText(
        'module.referral.inviteLanding.invitedTitle:{"maskedMobile":"155****0064"}',
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId('contact-side-rail')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'AI-Shifu' })).toHaveAttribute(
      'href',
      'https://official.example.com',
    );
    expect(
      screen.queryByLabelText('module.referral.inviteLanding.codeLabel'),
    ).not.toBeInTheDocument();
  });

  test('links the logo to the China official site when officialSiteUrl is blank', async () => {
    mockEnvState.officialSiteUrl = '   ';

    render(<ReferralInviteLanding initialInviteCode='ab12cd34' />);

    await waitFor(() =>
      expect(api.getReferralInvitePreview).toHaveBeenCalledWith(
        { invite_code: 'AB12CD34' },
        { skipErrorToast: true },
      ),
    );
    expect(screen.getByRole('link', { name: 'AI-Shifu' })).toHaveAttribute(
      'href',
      'https://ai-shifu.cn',
    );
  });

  test('redirects directly from invite-code route without re-entering code', async () => {
    render(<ReferralInviteLanding initialInviteCode='ab12cd34' />);

    fireEvent.click(
      await screen.findByRole('button', {
        name: /module\.referral\.inviteLanding\.register/,
      }),
    );

    await waitFor(() =>
      expect(api.recordReferralInviteEvent).toHaveBeenCalledWith(
        expect.objectContaining({
          event_type: 'registration_submitted',
          invite_code: 'AB12CD34',
          entry_source: 'invite_link',
        }),
        { skipErrorToast: true },
      ),
    );
    expect(mockPush).toHaveBeenCalledWith(
      expect.stringMatching(/^\/login\?invite_code=AB12CD34/),
    );
  });

  test('stores manual invite code and redirects to login', async () => {
    render(<ReferralInviteLanding />);

    fireEvent.change(
      screen.getByLabelText('module.referral.inviteLanding.codeLabel'),
      {
        target: { value: ' zz99 yy88 ' },
      },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: /module\.referral\.inviteLanding\.register/,
      }),
    );

    await waitFor(() =>
      expect(api.recordReferralInviteEvent).toHaveBeenCalledWith(
        expect.objectContaining({
          event_type: 'invite_code_entered',
          invite_code: 'ZZ99YY88',
          entry_source: 'manual_code',
        }),
        { skipErrorToast: true },
      ),
    );
    expect(mockPush).toHaveBeenCalledWith(
      expect.stringMatching(/^\/login\?invite_code=ZZ99YY88/),
    );
  });
});
