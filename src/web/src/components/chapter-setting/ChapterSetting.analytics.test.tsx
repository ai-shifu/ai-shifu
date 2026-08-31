import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import ChapterSettingsDialog from './ChapterSetting';

const mockGetOutlineInfo = jest.fn();
const mockModifyOutline = jest.fn();
const mockTrackEvent = jest.fn();

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getOutlineInfo: (...args: unknown[]) => mockGetOutlineInfo(...args),
    modifyOutline: (...args: unknown[]) => mockModifyOutline(...args),
  },
}));

jest.mock('@/c-api/studyV2', () => ({
  LEARNING_PERMISSION: {
    GUEST: 'guest',
    TRIAL: 'trial',
    NORMAL: 'normal',
  },
}));

jest.mock('@/store', () => ({
  useShifu: () => ({
    currentShifu: { bid: 'course-1', readonly: false },
  }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock('next/image', () => ({
  __esModule: true,
  default: function MockImage() {
    return null;
  },
}));

jest.mock('../loading', () => {
  const MockLoading = () => <div data-testid='settings-loading' />;
  MockLoading.displayName = 'MockLoading';
  return MockLoading;
});

jest.mock('@/components/ui/Sheet', () => ({
  Sheet: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SheetContent: ({
    children,
    onCloseIconClick,
  }: {
    children: React.ReactNode;
    onCloseIconClick?: () => void;
  }) => (
    <div>
      {children}
      <button
        type='button'
        aria-label='close-settings'
        onClick={onCloseIconClick}
      />
    </div>
  ),
  SheetHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SheetTitle: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, resolve, reject };
};

const variants = [
  {
    variant: 'lesson' as const,
    eventName: 'creator_outline_setting_save',
    payload: {
      shifu_bid: 'course-1',
      outline_bid: 'outline-1',
      save_type: 'manual',
      variant: 'lesson',
      learning_permission: 'trial',
      hide_chapter: false,
    },
  },
  {
    variant: 'chapter' as const,
    eventName: 'creator_outline_prompt_save',
    payload: {
      shifu_bid: 'course-1',
      outline_bid: 'outline-1',
      save_type: 'manual',
    },
  },
];

describe('ChapterSettingsDialog analytics producer', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetOutlineInfo.mockResolvedValue({
      type: 'trial',
      system_prompt: 'Private system prompt',
      is_hidden: false,
      name: 'Private outline title',
    });
  });

  it.each(variants)(
    'emits the exact $variant allowlist only after the save succeeds',
    async ({ variant, eventName, payload }) => {
      const save = createDeferred<void>();
      mockModifyOutline.mockReturnValue(save.promise);

      render(
        <ChapterSettingsDialog
          outlineBid='outline-1'
          open
          variant={variant}
        />,
      );

      const title = await screen.findByDisplayValue('Private outline title');
      fireEvent.change(title, { target: { value: 'Changed private title' } });
      fireEvent.click(screen.getByLabelText('close-settings'));

      await waitFor(() => expect(mockModifyOutline).toHaveBeenCalledTimes(1));
      expect(mockTrackEvent).not.toHaveBeenCalled();

      await act(async () => {
        save.resolve();
        await save.promise;
      });

      await waitFor(() => {
        expect(mockTrackEvent).toHaveBeenCalledWith(eventName, payload);
      });
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
      expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty('name');
      expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty(
        'system_prompt',
      );
      expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty('description');
    },
  );

  it.each(variants)(
    'does not emit $eventName when the $variant save fails',
    async ({ variant }) => {
      mockModifyOutline.mockRejectedValue(new Error('Private API error'));

      render(
        <ChapterSettingsDialog
          outlineBid='outline-1'
          open
          variant={variant}
        />,
      );

      const title = await screen.findByDisplayValue('Private outline title');
      fireEvent.change(title, { target: { value: 'Changed private title' } });
      fireEvent.click(screen.getByLabelText('close-settings'));

      await waitFor(() => expect(mockModifyOutline).toHaveBeenCalledTimes(1));
      await act(async () => {
        await Promise.resolve();
      });
      expect(mockTrackEvent).not.toHaveBeenCalled();
    },
  );
});
