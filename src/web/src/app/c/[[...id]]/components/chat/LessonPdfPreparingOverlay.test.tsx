import { render, screen } from '@testing-library/react';
import LessonPdfPreparingOverlay from './LessonPdfPreparingOverlay';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('LessonPdfPreparingOverlay', () => {
  it('makes the lesson page inert and restores focus after preparation', () => {
    const downloadLabel = 'download';
    const Harness = ({ open }: { open: boolean }) => (
      <>
        <div data-lesson-print-page='true'>
          <button type='button'>{downloadLabel}</button>
        </div>
        {open ? <LessonPdfPreparingOverlay /> : null}
      </>
    );
    const { rerender } = render(<Harness open={false} />);
    const downloadButton = screen.getByRole('button', {
      name: downloadLabel,
    });
    downloadButton.focus();

    rerender(<Harness open={true} />);

    const printPage = document.querySelector('[data-lesson-print-page="true"]');
    const dialog = screen.getByRole('dialog');
    expect(printPage).toHaveAttribute('inert');
    expect(printPage).toHaveAttribute('aria-hidden', 'true');
    expect(dialog).toHaveFocus();

    rerender(<Harness open={false} />);

    expect(printPage).not.toHaveAttribute('inert');
    expect(printPage).not.toHaveAttribute('aria-hidden');
    expect(downloadButton).toHaveFocus();
  });
});
