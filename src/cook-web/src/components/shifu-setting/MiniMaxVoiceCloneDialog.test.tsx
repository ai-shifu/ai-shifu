import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import MiniMaxVoiceCloneDialog from './MiniMaxVoiceCloneDialog';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getMinimaxTtsVoice: jest.fn(),
    submitMinimaxTtsVoiceClone: jest.fn(),
  },
}));

jest.mock('@/components/ui/Dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div>{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogFooter: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

function renderDialog() {
  return render(
    <MiniMaxVoiceCloneDialog
      open
      onOpenChange={jest.fn()}
      shifuId='shifu-1'
      cloneCost={{ can_submit: true, estimated_credits: '0' }}
      onRefreshCost={jest.fn().mockResolvedValue(undefined)}
      onVoiceChange={jest.fn()}
      onVoiceReady={jest.fn()}
    />,
  );
}

describe('MiniMaxVoiceCloneDialog', () => {
  beforeEach(() => {
    jest.restoreAllMocks();
  });

  test('does not render prompt audio controls', () => {
    const { container } = renderDialog();

    expect(
      screen.queryByText('module.shifuSetting.minimaxClonePromptAudio'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(
        'module.shifuSetting.minimaxClonePromptAudioDescription',
      ),
    ).not.toBeInTheDocument();
    expect(container.querySelector('#minimax-prompt-upload')).toBeNull();
  });

  test('does not render source upload controls', () => {
    const { container } = renderDialog();

    expect(
      screen.queryByText('module.shifuSetting.minimaxCloneUpload'),
    ).not.toBeInTheDocument();
    expect(container.querySelector('#minimax-source-upload')).toBeNull();
  });

  test('shows a friendly error when source recording permission fails', async () => {
    const getUserMedia = jest
      .fn()
      .mockRejectedValue(new Error('Permission denied'));
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    });
    Object.defineProperty(window, 'MediaRecorder', {
      configurable: true,
      value: jest.fn(),
    });

    renderDialog();

    fireEvent.click(screen.getByText('module.shifuSetting.minimaxCloneRecord'));

    await waitFor(() => {
      expect(screen.getByText('Permission denied')).toBeInTheDocument();
    });
    expect(getUserMedia).toHaveBeenCalledWith({ audio: true });
  });
});
