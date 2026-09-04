import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import {
  LiveVoiceFollowUpControls,
  LiveVoiceFollowUpMicrophoneButton,
} from './LiveVoiceFollowUpControls';
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
    <LiveVoiceFollowUpMicrophoneButton
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
    <>
      <LiveVoiceFollowUpMicrophoneButton
        controller={controller}
        target={target}
      />
      <LiveVoiceFollowUpControls
        controller={controller}
        target={target}
      />
    </>,
  );
  expect(
    screen.getByRole('button', { name: 'module.chat.liveVoiceRetry' }),
  ).toBeDisabled();
  expect(
    screen.getByRole('button', {
      name: 'module.chat.liveVoiceStartMicrophone',
    }),
  ).toBeDisabled();
  expect(screen.getByRole('alert')).toHaveTextContent(
    'module.chat.liveVoiceConnectionFailed',
  );
  expect(
    screen.queryByText('module.chat.liveVoiceRetryAvailableAt'),
  ).not.toBeInTheDocument();
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

it('shows a paused hint without enabling capture or resuming on panel render', () => {
  const controller = mockLiveVoiceController({
    anchorElementBid: 'anchor',
    open: true,
    state: 'listening',
    paused: true,
  });
  render(
    <>
      <LiveVoiceFollowUpMicrophoneButton
        controller={controller}
        target={target}
      />
      <LiveVoiceFollowUpControls
        controller={controller}
        target={target}
      />
    </>,
  );
  expect(screen.getByRole('status')).toHaveTextContent(
    'module.chat.liveVoicePaused',
  );
  expect(controller.start).not.toHaveBeenCalled();
  expect(controller.startMicrophone).not.toHaveBeenCalled();
  expect(controller.sendText).not.toHaveBeenCalled();
  const microphone = screen.getByRole('button', {
    name: 'module.chat.liveVoiceStartMicrophone',
  });
  expect(microphone).toBeEnabled();
  expect(microphone).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(microphone);
  expect(controller.startMicrophone).toHaveBeenCalledWith(target);
  fireEvent.click(
    screen.getByRole('button', { name: 'module.chat.liveVoiceEnd' }),
  );
  expect(controller.end).toHaveBeenCalledTimes(1);
});

it('does not expose internal session expiry or warnings', () => {
  render(
    <LiveVoiceFollowUpControls
      controller={mockLiveVoiceController({
        anchorElementBid: 'anchor',
        warning: true,
        endReason: 'timeout',
      })}
      target={target}
    />,
  );
  expect(screen.getByRole('status')).toHaveTextContent(
    'module.chat.liveVoiceInputHint',
  );
  expect(
    screen.queryByText('module.chat.liveVoiceTimeWarning'),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText('module.chat.liveVoiceTimedOut'),
  ).not.toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('does not show pause state belonging to another input anchor', () => {
  render(
    <LiveVoiceFollowUpControls
      controller={mockLiveVoiceController({
        anchorElementBid: 'another-anchor',
        open: true,
        state: 'listening',
        paused: true,
      })}
      target={target}
    />,
  );
  expect(screen.getByRole('status')).toHaveTextContent(
    'module.chat.liveVoiceInputHint',
  );
  expect(
    screen.queryByRole('button', { name: 'module.chat.liveVoiceEnd' }),
  ).not.toBeInTheDocument();
});

it('keeps microphone state and deliberate off analytics on the input action', () => {
  const controller = mockLiveVoiceController({
    anchorElementBid: 'anchor',
    open: true,
    state: 'listening',
    muted: false,
  });
  render(
    <LiveVoiceFollowUpMicrophoneButton
      controller={controller}
      target={target}
    />,
  );
  const microphone = screen.getByRole('button', {
    name: 'module.chat.liveVoiceStopMicrophone',
  });
  expect(microphone).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(microphone);
  expect(controller.stopMicrophone).toHaveBeenCalledWith(true);
});

it('does not duplicate the microphone below the input', () => {
  render(
    <LiveVoiceFollowUpControls
      controller={mockLiveVoiceController()}
      target={target}
    />,
  );
  expect(
    screen.queryByRole('button', {
      name: 'module.chat.liveVoiceStartMicrophone',
    }),
  ).not.toBeInTheDocument();
});
