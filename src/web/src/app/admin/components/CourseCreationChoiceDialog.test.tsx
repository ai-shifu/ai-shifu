import mockChinese from '../../../../../i18n/zh-CN/components/course-creation-choice-dialog.json';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import CourseCreationChoiceDialog from './CourseCreationChoiceDialog';

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
  test('presents prompt copying as the primary AI path and keeps the guide optional', async () => {
    const onAiCourseCreatorClick = jest.fn();
    const onAiCoursePromptCopy = jest.fn().mockResolvedValue(true);
    const onManualCreateClick = jest.fn();

    render(
      <CourseCreationChoiceDialog
        open
        onOpenChange={jest.fn()}
        courseCreatorUrl='https://creator.example.test/guide'
        onAiCourseCreatorClick={onAiCourseCreatorClick}
        onAiCoursePromptCopy={onAiCoursePromptCopy}
        onManualCreateClick={onManualCreateClick}
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

    fireEvent.click(
      screen.getByRole('button', {
        name: 'component.courseCreationChoiceDialog.manualAction',
      }),
    );
    expect(onManualCreateClick).toHaveBeenCalledTimes(1);
  });

  test('keeps prompt and manual creation available when the guide is unavailable', () => {
    render(
      <CourseCreationChoiceDialog
        open
        onOpenChange={jest.fn()}
        courseCreatorUrl={null}
        onAiCourseCreatorClick={jest.fn()}
        onAiCoursePromptCopy={jest.fn().mockResolvedValue(true)}
        onManualCreateClick={jest.fn()}
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
        onManualCreateClick={jest.fn()}
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
      onManualCreateClick: jest.fn(),
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
});
