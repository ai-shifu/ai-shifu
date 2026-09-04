import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { LiveVoiceFollowUpControls } from './LiveVoiceFollowUpControls';
import { mockLiveVoiceController } from './liveVoiceFollowUp.test-support';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en-US' },
  }),
}));
const target = { anchorElementBid: 'anchor', surface: 'read_content' as const };

it('renders compact manual controls without opening a dialog or microphone', () => {
  const controller = mockLiveVoiceController();
  render(
    <LiveVoiceFollowUpControls
      controller={controller}
      target={target}
    />,
  );
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(controller.start).not.toHaveBeenCalled();
  expect(controller.startMicrophone).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.chat.liveVoiceStartMicrophone',
    }),
  );
  expect(controller.startMicrophone).toHaveBeenCalledWith(target);
});

it('does not call microphone-off listening and keeps errors in the original input area', () => {
  const controller = mockLiveVoiceController({
    anchorElementBid: 'anchor',
    open: true,
    state: 'listening',
    microphoneError: 'microphone_denied',
  });
  render(
    <LiveVoiceFollowUpControls
      controller={controller}
      target={target}
    />,
  );
  expect(screen.getByRole('status')).toHaveTextContent(
    'module.chat.liveVoiceReady',
  );
  expect(screen.getByRole('alert')).toHaveTextContent(
    'module.chat.liveVoiceMicrophoneOptional',
  );
  fireEvent.click(
    screen.getByRole('button', { name: 'module.chat.liveVoiceEnd' }),
  );
  expect(controller.end).toHaveBeenCalledTimes(1);
});

it('retains the credential cooldown and explicit retry without another transport', () => {
  const controller = mockLiveVoiceController({
    anchorElementBid: 'anchor',
    errorCode: 'network_error',
    retryAvailableAt: Date.now() + 30000,
  });
  const { rerender } = render(
    <LiveVoiceFollowUpControls
      controller={controller}
      target={target}
    />,
  );
  expect(
    screen.getByRole('button', { name: 'module.chat.liveVoiceRetry' }),
  ).toBeDisabled();
  expect(
    screen.getByRole('button', {
      name: 'module.chat.liveVoiceStartMicrophone',
    }),
  ).toBeDisabled();
  rerender(
    <LiveVoiceFollowUpControls
      controller={{ ...controller, retryAvailableAt: null, retryable: true }}
      target={target}
    />,
  );
  fireEvent.click(
    screen.getByRole('button', { name: 'module.chat.liveVoiceRetry' }),
  );
  expect(controller.retry).toHaveBeenCalledTimes(1);
});
