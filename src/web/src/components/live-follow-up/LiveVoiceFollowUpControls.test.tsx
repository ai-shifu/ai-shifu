import { LIVE_FOLLOW_UP_CAPACITY_SCOPES } from '@/lib/liveVoiceCapacityScopes';
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

it('removes idle instructions and the inline privacy notice', () => {
  const { container } = render(
    <LiveVoiceFollowUpControls
      controller={mockLiveVoiceController()}
      target={target}
    />,
  );
  expect(container).toBeEmptyDOMElement();
  expect(
    screen.queryByText('module.chat.liveVoiceInputHint'),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText('module.chat.liveVoicePrivacyNotice'),
  ).not.toBeInTheDocument();
});

it.each(['checking', 'warming', 'unavailable'] as const)(
  'retains admission gates but shows only actual failures (%s)',
  readiness => {
    const controller = mockLiveVoiceController({
      readiness,
      anchorElementBid: 'anchor',
      errorCode: 'server_error',
      retryable: true,
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
    expect(
      screen.getByRole('button', {
        name: 'module.chat.liveVoiceStartMicrophone',
      }),
    ).toBeDisabled();
    expect(
      screen.queryByRole('button', { name: 'module.chat.liveVoiceRetry' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(
      'module.chat.liveVoiceErrors.server_error',
    );
    expect(
      screen.queryByText('module.chat.liveVoiceErrors.network_error'),
    ).not.toBeInTheDocument();
    expect(controller.startMicrophone).not.toHaveBeenCalled();
  },
);

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
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent(
    'module.chat.liveVoiceMicrophoneOptional',
  );
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});

it('retains the credential cooldown and recovers through the microphone rather than a retry button', () => {
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
    screen.queryByRole('button', { name: 'module.chat.liveVoiceRetry' }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole('button', {
      name: 'module.chat.liveVoiceStartMicrophone',
    }),
  ).toBeDisabled();
  expect(screen.getByRole('alert')).toHaveTextContent(
    'module.chat.liveVoiceErrors.network_error',
  );
  expect(
    screen.queryByText('module.chat.liveVoiceRetryAvailableAt'),
  ).not.toBeInTheDocument();
  rerender(
    <LiveVoiceFollowUpMicrophoneButton
      controller={{ ...controller, retryAvailableAt: null, retryable: true }}
      target={target}
    />,
  );
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.chat.liveVoiceStartMicrophone',
    }),
  );
  expect(controller.startMicrophone).toHaveBeenCalledWith(target);
  expect(controller.retry).not.toHaveBeenCalled();
});

it('shows no paused hint and resumes only through deliberate input', () => {
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
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
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
  expect(
    screen.queryByRole('button', { name: 'module.chat.liveVoiceEnd' }),
  ).not.toBeInTheDocument();
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
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
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
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
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

it('does not label an active usable connection as failed because its background readiness probe failed', () => {
  const { container } = render(
    <LiveVoiceFollowUpControls
      controller={mockLiveVoiceController({
        anchorElementBid: 'anchor',
        state: 'listening',
        readiness: 'unavailable',
      })}
      target={target}
    />,
  );
  expect(container).toBeEmptyDOMElement();
});

it.each([
  'connecting',
  'listening',
  'speaking',
  'reconnecting',
  'ended',
] as const)(
  'shows no extra information or session actions in normal state %s',
  state => {
    const { container } = render(
      <LiveVoiceFollowUpControls
        controller={mockLiveVoiceController({
          anchorElementBid: 'anchor',
          state,
          retryable: true,
        })}
        target={target}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  },
);

it.each(['checking', 'warming', 'ready'] as const)(
  'does not announce preparation (%s)',
  readiness => {
    const { container } = render(
      <LiveVoiceFollowUpControls
        controller={mockLiveVoiceController({ readiness })}
        target={target}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  },
);

it('animates only audible input, respects reduced motion, and always permits active microphone-off', () => {
  const controller = mockLiveVoiceController({
    anchorElementBid: 'anchor',
    muted: false,
    state: 'reconnecting',
    inputActive: true,
  });
  const { rerender } = render(
    <LiveVoiceFollowUpMicrophoneButton
      controller={controller}
      target={target}
    />,
  );
  const microphone = screen.getByRole('button');
  expect(microphone).toHaveClass('motion-safe:animate-pulse');
  expect(microphone).toBeEnabled();
  fireEvent.click(microphone);
  expect(controller.stopMicrophone).toHaveBeenCalledWith(true);
  rerender(
    <LiveVoiceFollowUpMicrophoneButton
      controller={{ ...controller, inputActive: false }}
      target={target}
    />,
  );
  expect(microphone).not.toHaveClass('motion-safe:animate-pulse');
  rerender(
    <LiveVoiceFollowUpMicrophoneButton
      controller={{ ...controller, muted: true }}
      target={target}
    />,
  );
  expect(microphone).not.toHaveClass('motion-safe:animate-pulse');
});

it.each([
  'microphone_denied',
  'microphone_unavailable',
  'microphone_busy',
  'audio_unavailable',
  'session_create_failed',
  'session_expired',
  'capacity_exceeded',
  'origin_rejected',
  'configuration_error',
  'network_error',
  'websocket_failed',
  'server_error',
  'unknown',
] as const)(
  'shows the specific %s error even when readiness is unavailable',
  errorCode => {
    render(
      <LiveVoiceFollowUpControls
        target={target}
        controller={mockLiveVoiceController({
          anchorElementBid: 'anchor',
          readiness: 'unavailable',
          state: 'ended',
          errorCode,
        })}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(
      `module.chat.liveVoiceErrors.${errorCode} (${errorCode})`,
    );
  },
);

it('shows the stable reason and close code but no raw provider description', () => {
  render(
    <LiveVoiceFollowUpControls
      target={target}
      controller={mockLiveVoiceController({
        anchorElementBid: 'anchor',
        errorCode: 'network_error',
        errorDiagnostic: { stage: 'websocket', websocketCloseCode: 1006 },
      })}
    />,
  );
  expect(screen.getByRole('alert')).toHaveTextContent(
    'network_error; WebSocket 1006',
  );
  expect(screen.getByRole('alert')).toHaveTextContent(
    'module.chat.liveVoiceErrorStages.websocket',
  );
});

it.each(LIVE_FOLLOW_UP_CAPACITY_SCOPES)(
  'shows capacity scope %s in the existing alert',
  scope => {
    render(
      <LiveVoiceFollowUpControls
        controller={mockLiveVoiceController({
          anchorElementBid: 'anchor',
          errorCode: 'capacity_exceeded',
          errorDiagnostic: {
            stage: 'session_create',
            reason: 'capacity_exceeded',
            capacityScopes: [scope],
          },
        })}
        target={target}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(
      `module.chat.liveVoiceCapacityScopes.${scope}`,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('(capacity_exceeded)');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  },
);
