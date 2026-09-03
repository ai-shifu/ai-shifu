import { fireEvent, render, screen } from '@testing-library/react';

import { LiveVoiceFollowUpDialog } from './LiveVoiceFollowUpDialog';
import type { LiveVoiceFollowUpController } from './useLiveVoiceFollowUp';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: { time?: string }) =>
      values?.time ? `${key}: ${values.time}` : key,
    i18n: { language: 'en-US' },
  }),
}));

const controller = (): LiveVoiceFollowUpController => ({
  open: true,
  state: 'ended',
  muted: false,
  warning: false,
  transcripts: [],
  errorCode: 'network_error',
  retryable: false,
  retryAvailableAt: Date.now() + 60_000,
  endReason: 'connection_error',
  start: jest.fn(),
  retry: jest.fn(),
  toggleMuted: jest.fn(),
  end: jest.fn(),
  close: jest.fn(),
});

describe('Live voice retry availability', () => {
  it('disables retry and displays the credential deadline until it is eligible', () => {
    const scrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = jest.fn();
    try {
      const value = controller();
      const { rerender } = render(
        <LiveVoiceFollowUpDialog controller={value} />,
      );
      const retry = screen.getByRole('button', {
        name: 'module.chat.liveVoiceRetry',
      });
      expect(retry).toBeDisabled();
      expect(
        screen.getByText(/module.chat.liveVoiceRetryAvailableAt/),
      ).toBeVisible();
      fireEvent.click(retry);
      expect(value.retry).not.toHaveBeenCalled();

      rerender(
        <LiveVoiceFollowUpDialog
          controller={{ ...value, retryable: true, retryAvailableAt: null }}
        />,
      );
      expect(retry).toBeEnabled();
      fireEvent.click(retry);
      expect(value.retry).toHaveBeenCalledTimes(1);
    } finally {
      Element.prototype.scrollIntoView = scrollIntoView;
    }
  });
});
