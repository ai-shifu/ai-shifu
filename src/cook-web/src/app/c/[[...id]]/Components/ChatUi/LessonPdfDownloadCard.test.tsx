import { fireEvent, render, screen } from '@testing-library/react';
import LessonPdfDownloadCard from './LessonPdfDownloadCard';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('LessonPdfDownloadCard', () => {
  it('keeps the entry visible but disabled while a follow-up is generating', () => {
    render(
      <LessonPdfDownloadCard
        isFollowUpStreaming={true}
        isPreparing={false}
        onDownload={jest.fn()}
      />,
    );

    expect(
      screen.getByRole('button', {
        name: 'module.chat.lessonPdfDownload',
      }),
    ).toBeDisabled();
    expect(
      screen.getByText('module.chat.lessonPdfFollowUpInProgress'),
    ).toBeInTheDocument();
  });

  it('starts PDF preparation from the download action', () => {
    const onDownload = jest.fn();
    render(
      <LessonPdfDownloadCard
        isFollowUpStreaming={false}
        isPreparing={false}
        onDownload={onDownload}
      />,
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.chat.lessonPdfDownload',
      }),
    );

    expect(onDownload).toHaveBeenCalledTimes(1);
    expect(
      screen.getByText('module.chat.lessonPdfPrintHint'),
    ).toBeInTheDocument();
  });
});
