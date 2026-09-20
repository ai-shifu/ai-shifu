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
let mockReadonly = false;

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getOutlineInfo: (...args: unknown[]) => mockGetOutlineInfo(...args),
    modifyOutline: (...args: unknown[]) => mockModifyOutline(...args),
  },
}));

jest.mock('@/api/studyV2', () => ({
  LEARNING_PERMISSION: {
    GUEST: 'guest',
    TRIAL: 'trial',
    NORMAL: 'normal',
  },
}));

jest.mock('@/store', () => ({
  useShifu: () => ({
    currentShifu: { bid: 'course-1', readonly: mockReadonly },
  }),
}));

jest.mock('@/hooks/useTracking', () => ({
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
      prompt_change: 'unchanged',
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
      prompt_change: 'unchanged',
    },
  },
];

describe('ChapterSettingsDialog', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockReadonly = false;
    mockTrackEvent.mockReset();
    mockModifyOutline.mockResolvedValue(undefined);
    mockGetOutlineInfo.mockResolvedValue({
      type: 'trial',
      system_prompt: 'Private system prompt',
      is_hidden: false,
      name: 'Private outline title',
    });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe.each(variants)('$variant prompt visibility', ({ variant }) => {
    it.each(['', '   ', '\n\t', null, undefined])(
      'hides the prompt section for an empty value (%p)',
      async systemPrompt => {
        mockGetOutlineInfo.mockResolvedValue({
          name: 'Private outline title',
          system_prompt: systemPrompt,
        });

        const { container } = render(
          <ChapterSettingsDialog
            outlineBid='outline-1'
            open
            variant={variant}
          />,
        );

        await screen.findByDisplayValue('Private outline title');
        expect(container.querySelector('textarea')).not.toBeInTheDocument();
        expect(
          screen.queryByText(`module.chapterSetting.${variant}Prompt`),
        ).not.toBeInTheDocument();
        expect(
          screen.queryByText(`module.chapterSetting.${variant}PromptHint`),
        ).not.toBeInTheDocument();
        expect(mockModifyOutline).not.toHaveBeenCalled();
        expect(mockTrackEvent).not.toHaveBeenCalled();
      },
    );
  });

  it.each(
    variants.flatMap(item =>
      (['manual', 'auto'] as const).flatMap(saveType =>
        [
          { blankType: 'empty', clearedPrompt: '' },
          { blankType: 'whitespace', clearedPrompt: ' \n\t' },
        ].map(blank => ({ ...item, saveType, ...blank })),
      ),
    ),
  )(
    'tracks a $blankType $variant prompt after a successful $saveType save',
    async ({ variant, eventName, payload, saveType, clearedPrompt }) => {
      const save = createDeferred<void>();
      mockModifyOutline.mockReturnValue(save.promise);

      const { container } = render(
        <ChapterSettingsDialog
          outlineBid='outline-1'
          open
          variant={variant}
        />,
      );

      const prompt = await screen.findByDisplayValue('Private system prompt');
      expect(prompt).toBeEnabled();
      jest.useFakeTimers();
      fireEvent.change(prompt, { target: { value: clearedPrompt } });
      expect(container.querySelector('textarea')).not.toBeInTheDocument();
      expect(mockTrackEvent).not.toHaveBeenCalled();

      if (saveType === 'auto') {
        await act(async () => {
          jest.advanceTimersByTime(3000);
        });
      } else {
        fireEvent.click(screen.getByLabelText('close-settings'));
      }
      expect(mockModifyOutline).toHaveBeenCalledWith(
        expect.objectContaining({
          outline_bid: 'outline-1',
          system_prompt: clearedPrompt,
        }),
      );
      expect(mockTrackEvent).not.toHaveBeenCalled();

      await act(async () => {
        save.resolve();
        await save.promise;
      });

      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
      expect(mockTrackEvent).toHaveBeenCalledWith(eventName, {
        ...payload,
        save_type: saveType,
        prompt_change: 'cleared',
      });
      expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty(
        'system_prompt',
      );
      expect(mockTrackEvent.mock.calls[0][1]).not.toHaveProperty('name');

      fireEvent.click(screen.getByLabelText('close-settings'));
      expect(mockModifyOutline).toHaveBeenCalledTimes(1);
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    },
  );

  describe.each(variants)(
    '$variant prompt outcomes',
    ({ variant, eventName, payload }) => {
      it('distinguishes substantive prompt edits from clearing', async () => {
        render(
          <ChapterSettingsDialog
            outlineBid='outline-1'
            open
            variant={variant}
          />,
        );
        const prompt = await screen.findByDisplayValue('Private system prompt');
        fireEvent.change(prompt, {
          target: { value: 'Updated private prompt' },
        });
        fireEvent.click(screen.getByLabelText('close-settings'));

        await waitFor(() =>
          expect(mockTrackEvent).toHaveBeenCalledWith(eventName, {
            ...payload,
            prompt_change: 'updated',
          }),
        );
        expect(mockTrackEvent).toHaveBeenCalledTimes(1);
      });

      it.each(['unchanged', 'readonly', 'invalid_title'])(
        'excludes %s forms from save analytics',
        async state => {
          mockReadonly = state === 'readonly';
          render(
            <ChapterSettingsDialog
              outlineBid='outline-1'
              open
              variant={variant}
            />,
          );
          const title = await screen.findByDisplayValue(
            'Private outline title',
          );
          if (state === 'invalid_title') {
            fireEvent.change(title, { target: { value: ' ' } });
          }
          fireEvent.click(screen.getByLabelText('close-settings'));
          expect(mockModifyOutline).not.toHaveBeenCalled();
          expect(mockTrackEvent).not.toHaveBeenCalled();
        },
      );

      it.each(['throw', 'reject'])(
        'still saves and closes when analytics fails by %s',
        async failure => {
          const onOpenChange = jest.fn();
          const onChange = jest.fn();
          mockTrackEvent.mockImplementation(() => {
            if (failure === 'throw') {
              throw new Error('Analytics unavailable');
            }
            return Promise.reject(new Error('Analytics unavailable'));
          });
          render(
            <ChapterSettingsDialog
              outlineBid='outline-1'
              open
              variant={variant}
              onOpenChange={onOpenChange}
              onChange={onChange}
            />,
          );
          const prompt = await screen.findByDisplayValue(
            'Private system prompt',
          );
          fireEvent.change(prompt, { target: { value: '' } });
          fireEvent.click(screen.getByLabelText('close-settings'));

          await waitFor(() =>
            expect(onOpenChange).toHaveBeenLastCalledWith(false),
          );
          expect(onChange).toHaveBeenCalledTimes(1);
          expect(mockModifyOutline).toHaveBeenCalledTimes(1);
          fireEvent.click(screen.getByLabelText('close-settings'));
          expect(mockModifyOutline).toHaveBeenCalledTimes(1);
        },
      );
    },
  );

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

      const prompt = await screen.findByDisplayValue('Private system prompt');
      fireEvent.change(prompt, { target: { value: '' } });
      fireEvent.click(screen.getByLabelText('close-settings'));

      await waitFor(() => expect(mockModifyOutline).toHaveBeenCalledTimes(1));
      await act(async () => {
        await Promise.resolve();
      });
      expect(mockTrackEvent).not.toHaveBeenCalled();
    },
  );
});
