import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import api from '@/api';
import { useBillingOverview } from '@/hooks/useBillingData';
import PreviewSettingsModal from './Preview';
import { showCreditInsufficientToast } from '@/lib/creditInsufficientToast';

const mockSaveMdflow = jest.fn();
const mockUseBillingOverview = useBillingOverview as jest.Mock;
const mockCurrentNode = {
  bid: 'lesson-1',
  depth: 1,
};
const mockCurrentShifu = {
  bid: 'shifu-1',
  readonly: false,
  created_user_bid: 'user-1',
};
const mockUserInfo = {
  user_bid: 'user-1',
  user_id: 'user-1',
};

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    previewShifu: jest.fn(),
  },
}));

jest.mock('@/hooks/useBillingData', () => ({
  useBillingOverview: jest.fn(),
}));

jest.mock('@/lib/creditInsufficientToast', () => ({
  DEBUG_DISABLED_BY_SOFTLIMIT_BUSINESS_CODE: 7125,
  resolveCourseCreditInsufficientAudience: ({
    previewMode,
    isCurrentUserCourseOwner,
  }: {
    previewMode: boolean;
    isCurrentUserCourseOwner: boolean;
  }) =>
    previewMode
      ? isCurrentUserCourseOwner
        ? 'teacher'
        : 'teacher-collaborator'
      : 'learner',
  showCreditInsufficientToast: jest.fn(),
}));

jest.mock('@/c-store', () => ({
  __esModule: true,
  useEnvStore: (selector: (state: { billingEnabled: string }) => unknown) =>
    selector({ billingEnabled: 'true' }),
}));

jest.mock('@/store', () => ({
  useShifu: () => ({
    currentNode: mockCurrentNode,
    currentShifu: mockCurrentShifu,
    actions: {
      saveMdflow: mockSaveMdflow,
    },
  }),
  useUserStore: (
    selector: (state: { userInfo: typeof mockUserInfo }) => unknown,
  ) => selector({ userInfo: mockUserInfo }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: jest.fn(),
  }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('PreviewSettingsModal', () => {
  beforeEach(() => {
    mockSaveMdflow.mockReset();
    (api.previewShifu as jest.Mock).mockReset();
    mockUseBillingOverview.mockReset();
    (showCreditInsufficientToast as jest.Mock).mockReset();
    mockCurrentNode.depth = 1;
    mockCurrentShifu.created_user_bid = 'user-1';
    mockUserInfo.user_bid = 'user-1';
    mockUserInfo.user_id = 'user-1';
  });

  it('shows a permanent purchase toast when billing softlimit blocks debug', async () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        debug_allowed: false,
      },
    });

    render(<PreviewSettingsModal />);

    const previewButton = screen.getByRole('button', {
      name: /module.preview.previewAll/,
    });
    expect(previewButton).toHaveAttribute('aria-disabled', 'true');

    await act(async () => {
      fireEvent.click(previewButton);
    });

    expect(mockSaveMdflow).not.toHaveBeenCalled();
    expect(api.previewShifu).not.toHaveBeenCalled();
    expect(showCreditInsufficientToast).toHaveBeenCalledWith({
      audience: 'teacher',
      code: 7125,
    });
  });

  it('disables preview while billing overview is loading', () => {
    mockUseBillingOverview.mockReturnValue({
      data: undefined,
    });

    render(<PreviewSettingsModal />);

    expect(
      screen.getByRole('button', {
        name: /module.preview.previewAll/,
      }),
    ).toBeDisabled();
  });

  it('starts preview when debug is allowed', async () => {
    mockUseBillingOverview.mockReturnValue({
      data: {
        debug_allowed: true,
      },
    });
    (api.previewShifu as jest.Mock).mockResolvedValue(
      'https://example.com/c/shifu-1?preview=true',
    );
    const openSpy = jest.spyOn(window, 'open').mockImplementation(() => null);

    render(<PreviewSettingsModal />);

    const previewButton = screen.getByRole('button', {
      name: /module.preview.previewAll/,
    });
    expect(previewButton).toBeEnabled();

    await act(async () => {
      fireEvent.click(previewButton);
    });

    await waitFor(() => {
      expect(mockSaveMdflow).toHaveBeenCalled();
      expect(api.previewShifu).toHaveBeenCalledWith(
        {
          shifu_bid: 'shifu-1',
          skip: false,
          variables: {},
        },
        {
          creditInsufficientAudience: 'teacher',
        },
      );
      expect(openSpy).toHaveBeenCalledWith(
        'https://example.com/c/shifu-1?preview=true&lessonid=lesson-1',
        '_blank',
        'noopener,noreferrer',
      );
    });

    openSpy.mockRestore();
  });

  it('lets collaborators reach the owner-billed preview with collaborator context', async () => {
    mockCurrentShifu.created_user_bid = 'course-owner-2';
    mockUseBillingOverview.mockReturnValue({
      data: {
        debug_allowed: false,
      },
    });
    (api.previewShifu as jest.Mock).mockResolvedValue(undefined);

    render(<PreviewSettingsModal />);

    const previewButton = screen.getByRole('button', {
      name: /module.preview.previewAll/,
    });
    expect(previewButton).toBeEnabled();
    await act(async () => {
      fireEvent.click(previewButton);
    });

    await waitFor(() => {
      expect(api.previewShifu).toHaveBeenCalledWith(
        {
          shifu_bid: 'shifu-1',
          skip: false,
          variables: {},
        },
        {
          creditInsufficientAudience: 'teacher-collaborator',
        },
      );
    });
    await waitFor(() => {
      expect(previewButton).toBeEnabled();
    });
    expect(showCreditInsufficientToast).not.toHaveBeenCalled();
  });

  it('removes a stale lessonid when previewing from a root node', async () => {
    mockCurrentNode.depth = 0;
    mockUseBillingOverview.mockReturnValue({
      data: {
        debug_allowed: true,
      },
    });
    (api.previewShifu as jest.Mock).mockResolvedValue(
      'https://example.com/c/shifu-1?preview=true&lessonid=stale-lesson',
    );
    const openSpy = jest.spyOn(window, 'open').mockImplementation(() => null);

    render(<PreviewSettingsModal />);
    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', {
          name: /module.preview.previewAll/,
        }),
      );
    });

    await waitFor(() => {
      expect(openSpy).toHaveBeenCalledWith(
        'https://example.com/c/shifu-1?preview=true',
        '_blank',
        'noopener,noreferrer',
      );
    });

    openSpy.mockRestore();
  });
});
