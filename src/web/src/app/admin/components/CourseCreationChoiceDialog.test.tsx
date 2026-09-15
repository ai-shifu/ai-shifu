import { fireEvent, render, screen } from '@testing-library/react';

import CourseCreationChoiceDialog from './CourseCreationChoiceDialog';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
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
      screen.getByText('component.courseCreationChoiceDialog.recommended'),
    ).toBeInTheDocument();
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
      'component.courseCreationChoiceDialog.aiPrompt',
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
});
