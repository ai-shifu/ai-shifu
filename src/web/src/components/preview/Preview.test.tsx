import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import api from '@/api';
import { useBillingOverview } from '@/hooks/use-billing-data';
import PreviewSettingsModal from './Preview';
import { showCreditInsufficientToast } from '@/lib/credit-insufficient-toast';

import { ShifuProvider, useShifu } from '@/store/use-shifu';

let mockUseRealShifu = false;
const mockSaveMdflow = jest.fn();
const mockTrackEvent = jest.fn();
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
const ownerUserInfo = {
  user_bid: 'user-1',
  user_id: 'user-1',
};
let mockUserInfo: typeof ownerUserInfo | null = ownerUserInfo;

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    previewShifu: jest.fn(),
    getShifuDetail: jest.fn(),
    getMdflow: jest.fn(),
    saveMdflow: jest.fn(),
    getProfileItemDefinitions: jest.fn(),
    getProfileVariableUsage: jest.fn(),
  },
}));

jest.mock('@/hooks/use-billing-data', () => ({
  useBillingOverview: jest.fn(),
}));

jest.mock('@/lib/credit-insufficient-toast', () => ({
  DEBUG_DISABLED_BY_SOFTLIMIT_BUSINESS_CODE: 7125,
  resolveCourseCreditInsufficientAudience: ({
    previewMode,
    isCurrentUserCourseOwner,
  }: {
    previewMode: boolean;
    isCurrentUserCourseOwner: boolean | null;
  }) => {
    if (!previewMode) {
      return 'learner';
    }
    if (isCurrentUserCourseOwner === null) {
      return null;
    }
    return isCurrentUserCourseOwner ? 'teacher' : 'teacher-collaborator';
  },
  showCreditInsufficientToast: jest.fn(),
}));

jest.mock('@/store', () => ({
  __esModule: true,
  useEnvStore: (selector: (state: { billingEnabled: string }) => unknown) =>
    selector({ billingEnabled: 'true' }),
  useShifu: () =>
    mockUseRealShifu
      ? jest.requireActual('@/store/use-shifu').useShifu()
      : {
          currentNode: mockCurrentNode,
          currentShifu: mockCurrentShifu,
          actions: {
            saveMdflow: mockSaveMdflow,
          },
        },
  useUserStore: (
    selector: (state: { userInfo: typeof ownerUserInfo | null }) => unknown,
  ) => selector({ userInfo: mockUserInfo }),
}));

jest.mock('@/hooks/use-tracking', () => ({
  useTracking: () => ({
    trackEvent: mockTrackEvent,
  }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('PreviewSettingsModal', () => {
  beforeEach(() => {
    mockUseRealShifu = false;
    mockSaveMdflow.mockReset();
    mockTrackEvent.mockReset();
    (api.previewShifu as jest.Mock).mockReset();
    mockUseBillingOverview.mockReset();
    (showCreditInsufficientToast as jest.Mock).mockReset();
    mockCurrentNode.depth = 1;
    mockCurrentShifu.created_user_bid = 'user-1';
    mockUserInfo = ownerUserInfo;
  });

  it('starts preview without writing a draft while lesson content is loading', async () => {
    mockUseRealShifu = true;
    mockUseBillingOverview.mockReturnValue({ data: { debug_allowed: true } });
    (api.getShifuDetail as jest.Mock).mockResolvedValue(mockCurrentShifu);
    (api.getProfileItemDefinitions as jest.Mock).mockResolvedValue([]);
    (api.getProfileVariableUsage as jest.Mock).mockResolvedValue({});
    (api.saveMdflow as jest.Mock).mockClear();
    let resolveContent!: (content: string) => void;
    (api.getMdflow as jest.Mock).mockReturnValue(
      new Promise<string>(resolve => {
        resolveContent = resolve;
      }),
    );

    let actions!: ReturnType<typeof useShifu>['actions'];
    function CourseEditor() {
      actions = useShifu().actions;
      return <PreviewSettingsModal />;
    }
    render(
      <ShifuProvider>
        <CourseEditor />
      </ShifuProvider>,
    );
    await act(async () => {
      await actions.loadShifu(mockCurrentShifu.bid);
    });
    let loading!: Promise<boolean>;
    act(() => {
      actions.setCurrentNode({
        id: 'lesson-1',
        bid: 'lesson-1',
        depth: 1,
        name: 'Lesson',
        position: '',
      });
      loading = actions.loadMdflow('lesson-1', mockCurrentShifu.bid);
    });
    expect(api.getMdflow).toHaveBeenCalledWith({
      shifu_bid: mockCurrentShifu.bid,
      outline_bid: 'lesson-1',
    });

    fireEvent.click(
      screen.getByRole('button', { name: 'module.preview.previewAll' }),
    );
    await waitFor(() => expect(api.previewShifu).toHaveBeenCalledTimes(1));
    expect(api.saveMdflow).not.toHaveBeenCalled();

    await act(async () => {
      resolveContent('Existing lesson content');
      expect(await loading).toBe(true);
    });
    expect(api.saveMdflow).not.toHaveBeenCalled();
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

  it('keeps preview disabled until the current user profile resolves', async () => {
    mockUserInfo = null;
    mockUseBillingOverview.mockReturnValue({
      data: {
        debug_allowed: true,
      },
    });

    const { rerender } = render(<PreviewSettingsModal />);

    const previewButton = screen.getByRole('button', {
      name: /module.preview.previewAll/,
    });
    expect(previewButton).toBeDisabled();

    await act(async () => {
      fireEvent.click(previewButton);
    });

    expect(mockSaveMdflow).not.toHaveBeenCalled();
    expect(api.previewShifu).not.toHaveBeenCalled();
    expect(showCreditInsufficientToast).not.toHaveBeenCalled();

    mockUserInfo = ownerUserInfo;
    rerender(<PreviewSettingsModal />);
    expect(previewButton).toBeEnabled();

    await act(async () => {
      fireEvent.click(previewButton);
    });
    expect(api.previewShifu).toHaveBeenCalledWith(
      expect.objectContaining({ shifu_bid: 'shifu-1' }),
      { creditInsufficientAudience: 'teacher' },
    );
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
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_shifu_preview_click',
        { shifu_bid: 'shifu-1' },
      );
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

  it('records the accepted click before saving the draft', async () => {
    let resolveSave: (() => void) | undefined;
    mockSaveMdflow.mockImplementation(
      () =>
        new Promise<void>(resolve => {
          resolveSave = resolve;
        }),
    );
    mockUseBillingOverview.mockReturnValue({
      data: {
        debug_allowed: true,
      },
    });

    render(<PreviewSettingsModal />);
    fireEvent.click(
      screen.getByRole('button', {
        name: /module.preview.previewAll/,
      }),
    );

    expect(mockTrackEvent).toHaveBeenCalledWith('creator_shifu_preview_click', {
      shifu_bid: 'shifu-1',
    });
    expect(api.previewShifu).not.toHaveBeenCalled();

    await act(async () => {
      resolveSave?.();
    });
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
