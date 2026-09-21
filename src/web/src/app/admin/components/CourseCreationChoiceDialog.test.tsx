import mockChinese from '../../../../../i18n/zh-CN/components/course-creation-choice-dialog.json';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import CourseCreationChoiceDialog from './CourseCreationChoiceDialog';
import { TITLE_MAX_LENGTH } from '@/constants/uiConstants';

let mockValidationGate: Promise<void> | undefined;

jest.mock('@hookform/resolvers/zod', () => {
  const actual = jest.requireActual('@hookform/resolvers/zod');
  return {
    ...actual,
    zodResolver: (...args: Parameters<typeof actual.zodResolver>) => {
      const resolver = actual.zodResolver(...args);
      return async (...values: Parameters<typeof resolver>) => {
        if (mockValidationGate) await mockValidationGate;
        return resolver(...values);
      };
    },
  };
});

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) =>
      key.endsWith('.aiPrompt') ? mockChinese.aiPrompt : key,
  }),
}));

jest.mock('@/lib/onboardingTargets', () => ({
  buildOnboardingTargetProps: () => ({}),
  ONBOARDING_TARGET_IDS: {
    lobsterCreateEntry: 'lobsterCreateEntry',
    blankCreateEntry: 'blankCreateEntry',
  },
}));

describe('CourseCreationChoiceDialog', () => {
  afterEach(() => {
    mockValidationGate = undefined;
  });

  test('presents both paths in one dialog and submits the inline manual form', async () => {
    const onAiCourseCreatorClick = jest.fn();
    const onAiCoursePromptCopy = jest.fn().mockResolvedValue(true);
    const onManualCreate = jest.fn();

    render(
      <CourseCreationChoiceDialog
        open
        onOpenChange={jest.fn()}
        courseCreatorUrl='https://creator.example.test/guide'
        onAiCourseCreatorClick={onAiCourseCreatorClick}
        onAiCoursePromptCopy={onAiCoursePromptCopy}
        onManualCreate={onManualCreate}
        onManualCreateCancel={jest.fn()}
      />,
    );

    expect(
      screen.queryByText('component.courseCreationChoiceDialog.recommended'),
    ).not.toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(
      screen.getByText('component.courseCreationChoiceDialog.aiDescription'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('component.courseCreationChoiceDialog.manualTitle'),
    ).toBeInTheDocument();

    const guideLink = screen.getByRole('link', {
      name: /component.courseCreationChoiceDialog.guideAction/,
    });
    expect(guideLink).toHaveAttribute(
      'href',
      'https://creator.example.test/guide',
    );
    expect(guideLink).toHaveAttribute('target', '_blank');
    fireEvent.click(guideLink);
    expect(onAiCourseCreatorClick).toHaveBeenCalledTimes(1);

    fireEvent.click(
      screen.getByRole('button', {
        name: /component.courseCreationChoiceDialog.copyAction/,
      }),
    );
    expect(onAiCoursePromptCopy).toHaveBeenCalledWith(
      '请帮我搜索并安装 AI 师傅的建课技能（ai-shifu-course-creator）。如果已经安装，请直接告诉我可以开始建课。',
    );
    expect(
      await screen.findByRole('button', {
        name: /component.courseCreationChoiceDialog.copiedAction/,
      }),
    ).toBeEnabled();

    fireEvent.change(
      screen.getByLabelText('component.createShifuDialog.nameLabel'),
      { target: { value: 'Course title' } },
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'component.courseCreationChoiceDialog.manualAction',
      }),
    );
    await waitFor(() =>
      expect(onManualCreate).toHaveBeenCalledWith({
        name: 'Course title',
        description: '',
        avatar: '',
      }),
    );
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
  });

  test('keeps prompt and manual creation available when the guide is unavailable', () => {
    render(
      <CourseCreationChoiceDialog
        open
        onOpenChange={jest.fn()}
        courseCreatorUrl={null}
        onAiCourseCreatorClick={jest.fn()}
        onAiCoursePromptCopy={jest.fn().mockResolvedValue(true)}
        onManualCreate={jest.fn()}
        onManualCreateCancel={jest.fn()}
      />,
    );

    expect(
      screen.queryByRole('link', {
        name: /component.courseCreationChoiceDialog.guideAction/,
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: /component.courseCreationChoiceDialog.copyAction/,
      }),
    ).toBeEnabled();
    expect(
      screen.getByRole('button', {
        name: 'component.courseCreationChoiceDialog.manualAction',
      }),
    ).toBeEnabled();
  });

  test('ignores pending clicks, allows retry, and changes guidance only on success', async () => {
    let settle!: (value: boolean) => void;
    const copy = jest
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<boolean>(resolve => {
            settle = resolve;
          }),
      )
      .mockResolvedValue(true);
    render(
      <CourseCreationChoiceDialog
        open
        onOpenChange={jest.fn()}
        courseCreatorUrl={null}
        onAiCourseCreatorClick={jest.fn()}
        onAiCoursePromptCopy={copy}
        onManualCreate={jest.fn()}
        onManualCreateCancel={jest.fn()}
      />,
    );
    const button = screen.getByRole('button', { name: /\.copyAction/ });
    fireEvent.click(button);
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(copy).toHaveBeenCalledTimes(1);
    await act(async () => settle(false));
    expect(button).toBeEnabled();
    expect(screen.getByRole('status')).toHaveTextContent(
      'component.courseCreationChoiceDialog.copyHint',
    );
    fireEvent.click(button);
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(
        'component.courseCreationChoiceDialog.copySuccessDescription',
      ),
    );
    expect(copy).toHaveBeenCalledTimes(2);
  });

  test('closing resets success and ignores an earlier pending copy after reopening', async () => {
    let settle!: (value: boolean) => void;
    const copy = jest
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<boolean>(resolve => {
            settle = resolve;
          }),
      )
      .mockResolvedValue(true);
    const props = {
      onOpenChange: jest.fn(),
      courseCreatorUrl: null,
      onAiCourseCreatorClick: jest.fn(),
      onAiCoursePromptCopy: copy,
      onManualCreate: jest.fn(),
      onManualCreateCancel: jest.fn(),
    };
    const { rerender } = render(
      <CourseCreationChoiceDialog
        {...props}
        open
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /\.copyAction/ }));
    rerender(
      <CourseCreationChoiceDialog
        {...props}
        open={false}
      />,
    );
    rerender(
      <CourseCreationChoiceDialog
        {...props}
        open
      />,
    );
    await act(async () => settle(true));
    expect(screen.getByRole('button', { name: /\.copyAction/ })).toBeEnabled();
    expect(screen.getByRole('status')).toHaveTextContent(
      'component.courseCreationChoiceDialog.copyHint',
    );
    fireEvent.click(screen.getByRole('button', { name: /\.copyAction/ }));
    await screen.findByRole('button', { name: /\.copiedAction/ });
    rerender(
      <CourseCreationChoiceDialog
        {...props}
        open={false}
      />,
    );
    rerender(
      <CourseCreationChoiceDialog
        {...props}
        open
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent(
      'component.courseCreationChoiceDialog.copyHint',
    );
  });

  test('validates the name before submission and clears fields and errors on reopen', async () => {
    const props = {
      onOpenChange: jest.fn(),
      courseCreatorUrl: null,
      onAiCourseCreatorClick: jest.fn(),
      onAiCoursePromptCopy: jest.fn().mockResolvedValue(true),
      onManualCreate: jest.fn(),
      onManualCreateCancel: jest.fn(),
    };
    const { rerender } = render(
      <CourseCreationChoiceDialog
        {...props}
        open
      />,
    );
    expect(
      screen.getByLabelText('component.createShifuDialog.nameLabel'),
    ).toHaveAttribute('maxlength', String(TITLE_MAX_LENGTH));
    expect(
      screen.getByLabelText('component.createShifuDialog.descriptionLabel'),
    ).toHaveAttribute('maxlength', '300');
    fireEvent.change(
      screen.getByLabelText('component.createShifuDialog.descriptionLabel'),
      {
        target: { value: 'Draft introduction' },
      },
    );
    fireEvent.click(screen.getByRole('button', { name: /\.manualAction/ }));
    expect(
      await screen.findByText('component.createShifuDialog.nameRequired'),
    ).toBeInTheDocument();
    expect(props.onManualCreate).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(
        screen.getByLabelText('component.createShifuDialog.nameLabel'),
      ).toHaveFocus(),
    );

    rerender(
      <CourseCreationChoiceDialog
        {...props}
        open={false}
      />,
    );
    rerender(
      <CourseCreationChoiceDialog
        {...props}
        open
      />,
    );
    expect(
      screen.getByLabelText('component.createShifuDialog.descriptionLabel'),
    ).toHaveValue('');
    expect(
      screen.queryByText('component.createShifuDialog.nameRequired'),
    ).not.toBeInTheDocument();
    expect(props.onManualCreateCancel).not.toHaveBeenCalled();
  });

  test('blocks duplicate submissions and dismissal until the pending creation settles', async () => {
    let settle!: () => void;
    const props = {
      onOpenChange: jest.fn(),
      courseCreatorUrl: null,
      onAiCourseCreatorClick: jest.fn(),
      onAiCoursePromptCopy: jest.fn().mockResolvedValue(true),
      onManualCreate: jest.fn().mockImplementation(
        () =>
          new Promise<void>(resolve => {
            settle = resolve;
          }),
      ),
      onManualCreateCancel: jest.fn(),
    };
    render(
      <CourseCreationChoiceDialog
        {...props}
        open
      />,
    );
    const name = screen.getByLabelText('component.createShifuDialog.nameLabel');
    fireEvent.change(name, { target: { value: 'Course title' } });
    // Submit the form directly too, exercising the guard beyond the disabled button.
    const form = name.closest('form')!;
    fireEvent.submit(form);
    await waitFor(() => expect(props.onManualCreate).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('button', { name: /\.creating/ })).toBeDisabled();
    expect(name).toHaveAttribute('readonly');
    expect(
      screen.queryByRole('button', { name: 'component.header.close' }),
    ).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.submit(form);
    });
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(props.onManualCreate).toHaveBeenCalledTimes(1);
    expect(props.onOpenChange).not.toHaveBeenCalled();
    expect(props.onManualCreateCancel).not.toHaveBeenCalled();
    await act(async () => settle());
    expect(
      screen.getByRole('button', { name: /\.manualAction/ }),
    ).toBeEnabled();
    expect(name).toHaveValue('Course title');
    fireEvent.click(
      screen.getByRole('button', { name: 'component.header.close' }),
    );
    expect(props.onOpenChange).toHaveBeenCalledWith(false);
    expect(props.onManualCreateCancel).toHaveBeenCalledTimes(1);
  });

  test.each(['valid', 'invalid'])(
    'locks dismissal before asynchronous %s validation and releases after settlement',
    async validity => {
      let finishValidation!: () => void;
      let finishCreation!: () => void;
      mockValidationGate = new Promise<void>(resolve => {
        finishValidation = resolve;
      });
      const props = {
        onOpenChange: jest.fn(),
        courseCreatorUrl: null,
        onAiCourseCreatorClick: jest.fn(),
        onAiCoursePromptCopy: jest.fn().mockResolvedValue(true),
        onManualCreate: jest.fn().mockImplementation(
          () =>
            new Promise<void>(resolve => {
              finishCreation = resolve;
            }),
        ),
        onManualCreateCancel: jest.fn(),
      };
      render(
        <CourseCreationChoiceDialog
          {...props}
          open
        />,
      );
      const name = screen.getByLabelText(
        'component.createShifuDialog.nameLabel',
      );
      if (validity === 'valid') {
        fireEvent.change(name, { target: { value: 'Course title' } });
      }
      const form = name.closest('form')!;
      fireEvent.submit(form);
      fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
      fireEvent.submit(form);
      expect(props.onManualCreate).not.toHaveBeenCalled();
      expect(props.onOpenChange).not.toHaveBeenCalled();
      expect(props.onManualCreateCancel).not.toHaveBeenCalled();
      expect(
        screen.queryByRole('button', { name: 'component.header.close' }),
      ).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /\.creating/ })).toBeDisabled();

      await act(async () => finishValidation());
      if (validity === 'valid') {
        expect(props.onManualCreate).toHaveBeenCalledTimes(1);
        fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
        expect(props.onOpenChange).not.toHaveBeenCalled();
        await act(async () => finishCreation());
      } else {
        expect(props.onManualCreate).not.toHaveBeenCalled();
        expect(
          await screen.findByText('component.createShifuDialog.nameRequired'),
        ).toBeInTheDocument();
        await waitFor(() => expect(name).toHaveFocus());
      }

      expect(name).not.toHaveAttribute('readonly');
      expect(
        screen.getByRole('button', { name: /\.manualAction/ }),
      ).toBeEnabled();
      fireEvent.click(
        screen.getByRole('button', { name: 'component.header.close' }),
      );
      expect(props.onOpenChange).toHaveBeenCalledWith(false);
      expect(props.onManualCreateCancel).toHaveBeenCalledTimes(1);
    },
  );
});
