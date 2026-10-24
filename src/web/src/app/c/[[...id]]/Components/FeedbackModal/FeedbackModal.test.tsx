import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { submitFeedback } from '@/api/bz';
import { toast } from '@/hooks/useToast';
import { FeedbackModal } from './FeedbackModal';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock('@/api/bz', () => ({ submitFeedback: jest.fn() }));
jest.mock('@/hooks/useToast', () => ({ toast: jest.fn() }));
jest.mock('@/lib/request', () => ({ getRequestFallbackMessage: jest.fn() }));

describe('FeedbackModal validation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.mocked(submitFeedback).mockResolvedValue(undefined);
  });

  it.each(['', '1234'])(
    'shows the minimum-length message for %p and submits after correction',
    async invalidFeedback => {
      const onClose = jest.fn();
      render(
        <FeedbackModal
          open
          onClose={onClose}
        />,
      );

      const input = screen.getByPlaceholderText(
        'module.feedback.feedbackPlaceholder',
      );
      const submit = screen.getByRole('button', {
        name: 'module.feedback.feedbackSubmit',
      });
      fireEvent.change(input, { target: { value: invalidFeedback } });
      fireEvent.click(submit);

      expect(
        await screen.findByText('module.feedback.feedbackPlaceholder'),
      ).toBeInTheDocument();
      expect(input).toHaveAttribute('aria-invalid', 'true');
      expect(submitFeedback).not.toHaveBeenCalled();
      expect(toast).not.toHaveBeenCalled();
      expect(onClose).not.toHaveBeenCalled();

      fireEvent.change(input, { target: { value: '12345' } });
      fireEvent.click(submit);

      await waitFor(() => {
        expect(submitFeedback).toHaveBeenCalledTimes(1);
        expect(submitFeedback).toHaveBeenCalledWith('12345');
        expect(toast).toHaveBeenCalledWith({
          title: 'module.feedback.feedbackSuccess',
        });
        expect(onClose).toHaveBeenCalledTimes(1);
        expect(
          screen.queryByText('module.feedback.feedbackPlaceholder'),
        ).not.toBeInTheDocument();
        expect(input).toHaveAttribute('aria-invalid', 'false');
        expect(input).toHaveValue('');
      });
    },
  );
});
