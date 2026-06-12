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
    recordReferralInviteEvent: jest.fn(),
  },
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => `module.referral.${key}`,
  }),
}));

describe('ReferralInviteLanding', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    window.localStorage.clear();
    (api.recordReferralInviteEvent as jest.Mock).mockResolvedValue({
      success: true,
      session_id: 'session-1',
      recognized: true,
    });
  });

  test('records link and page view events for invite-code route', async () => {
    render(<ReferralInviteLanding initialInviteCode='ab12cd34' />);

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
        name: /module\.referral\.inviteLanding\.continue/,
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
