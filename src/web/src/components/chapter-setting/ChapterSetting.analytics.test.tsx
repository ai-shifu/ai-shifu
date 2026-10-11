import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import ChapterSettingsDialog from './ChapterSetting';
import type { LearningPermission } from '@/api/studyV2';

const mockGetOutlineInfo = jest.fn();
const mockModifyOutline = jest.fn();
const mockTrackEvent = jest.fn();
let mockReadonly = false;
let mockDefaultLearningPermission: LearningPermission | undefined = 'trial';

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
    currentShifu: {
      bid: 'course-1',
      readonly: mockReadonly,
      default_learning_permission: mockDefaultLearningPermission,
    },
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
    mockDefaultLearningPermission = 'trial';
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

  describe('backend-owned creation defaults', () => {
    const permissionOptions = () =>
      within(screen.getAllByRole('radiogroup')[0]);
    const fillLessonName = () =>
      fireEvent.change(
        screen.getByPlaceholderText(
          'module.chapterSetting.lessonNamePlaceholder',
        ),
        { target: { value: 'New lesson' } },
      );

    it.each(['guest', 'trial', 'normal'] as const)(
      'displays the backend %s default and omits an unchanged permission',
      permission => {
        mockDefaultLearningPermission = permission;
        const onFooterAction = jest.fn();
        render(
          <ChapterSettingsDialog
            open
            footerActionLabel='Create lesson'
            onFooterAction={onFooterAction}
          />,
        );
        expect(
          permissionOptions().getByRole('radio', { checked: true }),
        ).toHaveAttribute('value', permission);
        fillLessonName();
        fireEvent.click(screen.getByRole('button', { name: 'Create lesson' }));

        expect(onFooterAction).toHaveBeenCalledWith({
          name: 'New lesson',
          isHidden: false,
          systemPrompt: '',
        });
        expect(mockGetOutlineInfo).not.toHaveBeenCalled();
        expect(mockModifyOutline).not.toHaveBeenCalled();
        expect(mockTrackEvent).not.toHaveBeenCalled();
      },
    );

    it.each(['guest', 'normal'] as const)(
      'passes an explicit %s selection',
      permission => {
        const onFooterAction = jest.fn();
        render(
          <ChapterSettingsDialog
            open
            footerActionLabel='Create lesson'
            onFooterAction={onFooterAction}
          />,
        );
        fillLessonName();
        fireEvent.click(
          screen.getByRole('radio', {
            name: `module.chapterSetting.${permission === 'normal' ? 'paid' : 'guest'}`,
          }),
        );
        fireEvent.click(screen.getByRole('button', { name: 'Create lesson' }));

        expect(onFooterAction).toHaveBeenCalledWith(
          expect.objectContaining({ learningPermission: permission }),
        );
      },
    );

    it('does not invent a frontend default when backend metadata is unavailable', () => {
      mockDefaultLearningPermission = undefined;
      const onFooterAction = jest.fn();
      render(
        <ChapterSettingsDialog
          open
          footerActionLabel='Create lesson'
          onFooterAction={onFooterAction}
        />,
      );
      expect(
        permissionOptions().queryByRole('radio', { checked: true }),
      ).not.toBeInTheDocument();
      fillLessonName();
      fireEvent.click(screen.getByRole('button', { name: 'Create lesson' }));
      expect(onFooterAction.mock.calls[0][0]).not.toHaveProperty(
        'learningPermission',
      );
    });

    it('resets a reopened form to the current backend metadata', () => {
      const onFooterAction = jest.fn();
      const { rerender } = render(
        <ChapterSettingsDialog
          open
          footerActionLabel='Create lesson'
          onFooterAction={onFooterAction}
        />,
      );
      fillLessonName();
      fireEvent.click(
        screen.getByRole('radio', { name: 'module.chapterSetting.guest' }),
      );
      rerender(
        <ChapterSettingsDialog
          open={false}
          footerActionLabel='Create lesson'
          onFooterAction={onFooterAction}
        />,
      );
      mockDefaultLearningPermission = 'normal';
      rerender(
        <ChapterSettingsDialog
          open
          footerActionLabel='Create lesson'
          onFooterAction={onFooterAction}
        />,
      );
      expect(
        permissionOptions().getByRole('radio', { checked: true }),
      ).toHaveAttribute('value', 'normal');
      expect(
        screen.getByPlaceholderText(
          'module.chapterSetting.lessonNamePlaceholder',
        ),
      ).toHaveValue('');
      fillLessonName();
      fireEvent.click(screen.getByRole('button', { name: 'Create lesson' }));
      expect(onFooterAction.mock.calls[0][0]).not.toHaveProperty(
        'learningPermission',
      );
    });

    it('keeps an existing lesson permission instead of the creation default', async () => {
      mockGetOutlineInfo.mockResolvedValue({
        name: 'Existing lesson',
        type: 'guest',
        is_hidden: false,
      });
      render(
        <ChapterSettingsDialog
          open
          outlineBid='outline-1'
        />,
      );
      const name = await screen.findByDisplayValue('Existing lesson');
      expect(
        permissionOptions().getByRole('radio', { checked: true }),
      ).toHaveAttribute('value', 'guest');
      fireEvent.change(name, { target: { value: 'Renamed lesson' } });
      fireEvent.click(screen.getByLabelText('close-settings'));
      await waitFor(() =>
        expect(mockModifyOutline).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'guest',
            is_paid: false,
            require_login: false,
          }),
        ),
      );
      expect(mockTrackEvent).toHaveBeenCalledWith(
        'creator_outline_setting_save',
        expect.objectContaining({ learning_permission: 'guest' }),
      );
    });

    it('saves chapter changes when no permission metadata is available', async () => {
      mockDefaultLearningPermission = undefined;
      mockGetOutlineInfo.mockResolvedValue({ name: 'Existing chapter' });
      render(
        <ChapterSettingsDialog
          open
          variant='chapter'
          outlineBid='outline-1'
        />,
      );
      const name = await screen.findByDisplayValue('Existing chapter');
      fireEvent.change(name, { target: { value: 'Renamed chapter' } });
      fireEvent.click(screen.getByLabelText('close-settings'));
      await waitFor(() =>
        expect(mockModifyOutline).toHaveBeenCalledWith(
          expect.objectContaining({ name: 'Renamed chapter' }),
        ),
      );
      expect(mockModifyOutline.mock.calls[0][0]).not.toHaveProperty('type');
    });
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
