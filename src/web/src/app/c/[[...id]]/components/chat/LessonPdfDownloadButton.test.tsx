import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LessonPdfDownloadButton from './LessonPdfDownloadButton';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('LessonPdfDownloadButton', () => {
  it('keeps the action visible while lesson content is still generating', async () => {
    const onDownload = jest.fn();
    const user = userEvent.setup();
    render(
      <LessonPdfDownloadButton
        isContentReady={false}
        isFollowUpStreaming={false}
        isPreparing={false}
        onDownload={onDownload}
      />,
    );

    const button = screen.getByRole('button', {
      name: 'module.chat.lessonPdfDownload',
    });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(button);
    expect(onDownload).not.toHaveBeenCalled();

    await act(async () => {
      await user.hover(button);
    });
    expect(
      await screen.findAllByText('module.chat.lessonPdfContentInProgress'),
    ).not.toHaveLength(0);
  });

  it('keeps the unavailable action focusable and explains why it is disabled', async () => {
    const onDownload = jest.fn();
    const user = userEvent.setup();
    render(
      <LessonPdfDownloadButton
        isContentReady={true}
        isFollowUpStreaming={true}
        isPreparing={false}
        onDownload={onDownload}
      />,
    );

    const button = screen.getByRole('button', {
      name: 'module.chat.lessonPdfDownload',
    });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(button).not.toHaveTextContent('module.chat.lessonPdfDownload');
    expect(button.querySelector('svg')).toBeInTheDocument();
    fireEvent.click(button);
    expect(onDownload).not.toHaveBeenCalled();

    await act(async () => {
      await user.tab();
    });
    expect(button).toHaveFocus();
    expect(
      await screen.findAllByText('module.chat.lessonPdfFollowUpInProgress'),
    ).not.toHaveLength(0);
  });

  it('starts PDF preparation from the icon-only titlebar action', async () => {
    const onDownload = jest.fn();
    const user = userEvent.setup();
    render(
      <LessonPdfDownloadButton
        isContentReady={true}
        isFollowUpStreaming={false}
        isPreparing={false}
        onDownload={onDownload}
      />,
    );

    const button = screen.getByRole('button', {
      name: 'module.chat.lessonPdfDownload',
    });
    fireEvent.click(button);

    expect(onDownload).toHaveBeenCalledTimes(1);
    expect(button).not.toHaveTextContent('module.chat.lessonPdfDownload');
    await act(async () => {
      await user.hover(button);
    });
    expect(
      await screen.findAllByText('module.chat.lessonPdfPrintHint'),
    ).not.toHaveLength(0);
  });

  it('announces the preparing state and prevents duplicate downloads', () => {
    render(
      <LessonPdfDownloadButton
        isContentReady={true}
        isFollowUpStreaming={false}
        isPreparing={true}
        onDownload={jest.fn()}
      />,
    );

    const button = screen.getByRole('button', {
      name: 'module.chat.lessonPdfPreparing',
    });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(button).toHaveAttribute('aria-busy', 'true');
  });
});
