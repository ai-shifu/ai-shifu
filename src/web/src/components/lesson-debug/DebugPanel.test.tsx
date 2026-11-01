import React from 'react';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import DebugPanel from './DebugPanel';
import { resolveDebugItemKey } from './DebugPanel';
import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';

const mockPush = jest.fn();
const mockCopyText = jest.fn();
const mockDebugVariablesPanel = jest.fn();
const mockTrackEvent = jest.fn();

jest.mock('@/hooks/use-tracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('next/image', () => ({
  __esModule: true,
  default: ({ alt, src }: { alt: string; src: string }) =>
    React.createElement('img', { alt, src }),
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('@/components/ui/AlertProvider', () => ({
  useAlert: () => ({
    showAlert: jest.fn(),
  }),
}));

jest.mock('@/components/ui/Tooltip', () => {
  const React = jest.requireActual('react');
  const TooltipProviderContext = React.createContext(false);

  return {
    TooltipProvider: ({ children }: { children: React.ReactNode }) =>
      React.createElement(
        TooltipProviderContext.Provider,
        { value: true },
        children,
      ),
    Tooltip: ({ children }: { children: React.ReactNode }) => {
      if (!React.useContext(TooltipProviderContext)) {
        throw new Error('`Tooltip` must be used within `TooltipProvider`');
      }
      return <div>{children}</div>;
    },
    TooltipContent: ({ children }: { children: React.ReactNode }) => (
      <div role='tooltip'>{children}</div>
    ),
    TooltipTrigger: ({ children }: { children: React.ReactNode }) => (
      <>{children}</>
    ),
  };
});

jest.mock('@/lib/text-utils', () => {
  const actual = jest.requireActual('@/lib/text-utils');
  return {
    ...actual,
    copyText: (...args: unknown[]) => mockCopyText(...args),
  };
});

jest.mock('@/components/ui/Dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogDescription: ({ children }: { children: React.ReactNode }) => (
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

jest.mock('@/components/chat/ContentBlock', () => ({
  __esModule: true,
  default: ({
    item,
    blockBid,
    contentRenderKey,
    enableStreamingTypewriter,
    onTypeFinished,
  }: {
    item: ChatContentItem;
    blockBid: string;
    contentRenderKey?: string;
    enableStreamingTypewriter?: boolean;
    onTypeFinished?: (blockBid: string, content: string) => void;
  }) => (
    <div
      data-testid={item.element_bid}
      data-content-render-key={contentRenderKey}
    >
      <span>{item.content}</span>
      {enableStreamingTypewriter ? <span>typing</span> : null}
      {onTypeFinished ? (
        <button
          type='button'
          onClick={() => onTypeFinished(blockBid, item.content || '')}
        >
          finish-{blockBid}
        </button>
      ) : null}
    </div>
  ),
}));

jest.mock('@/components/chat/InteractionBlock', () => ({
  __esModule: true,
  default: ({
    element_bid,
    showGenerateBtn,
    onRefresh,
    disabled,
    extraActions,
  }: {
    element_bid?: string;
    showGenerateBtn?: boolean;
    onRefresh?: (elementBid: string) => void;
    disabled?: boolean;
    extraActions?: React.ReactNode;
  }) => (
    <div data-testid='interaction-block'>
      <span>{element_bid}</span>
      {showGenerateBtn ? (
        <button
          type='button'
          aria-label={`regenerate-${element_bid}`}
          disabled={disabled}
          onClick={() => onRefresh?.(element_bid || '')}
        />
      ) : null}
      <div data-testid={`actions-${element_bid}`}>{extraActions}</div>
    </div>
  ),
}));

jest.mock('@/components/audio/AudioPlayer', () => ({
  __esModule: true,
  AudioPlayer: ({
    disabled,
    onRequestAudio,
  }: {
    disabled?: boolean;
    onRequestAudio?: () => Promise<unknown>;
  }) => (
    <button
      type='button'
      aria-label='audio'
      disabled={disabled}
      onClick={() => void onRequestAudio?.()}
    />
  ),
}));

jest.mock('./DebugVariablesPanel', () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => {
    mockDebugVariablesPanel(props);
    return null;
  },
}));

describe('DebugPanel billing action', () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockCopyText.mockReset();
    mockDebugVariablesPanel.mockReset();
    mockTrackEvent.mockReset();
  });

  test('offers regeneration retry when no generated output remains', () => {
    const onRetryRegeneration = jest.fn();

    render(
      <DebugPanel
        isLoading={false}
        items={[]}
        shifuBid='shifu-1'
        onRegenerate={jest.fn()}
        onRetryRegeneration={onRetryRegeneration}
        onSubmitInteraction={jest.fn()}
      />,
    );

    expect(
      screen.queryByText('module.shifu.previewArea.empty'),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'common.core.retry' }));
    expect(onRetryRegeneration).toHaveBeenCalledTimes(1);
  });

  test('only offers regeneration retry when available and idle', () => {
    const onRetryRegeneration = jest.fn();
    const props = {
      items: [
        {
          element_bid: 'debug-error',
          content: 'Regeneration failed',
          type: ChatContentItemType.ERROR,
        },
      ],
      shifuBid: 'shifu-1',
      onRegenerate: jest.fn(),
      onSubmitInteraction: jest.fn(),
    };
    const { rerender } = render(
      <DebugPanel
        {...props}
        isLoading={false}
      />,
    );
    expect(
      screen.queryByRole('button', { name: 'common.core.retry' }),
    ).not.toBeInTheDocument();

    rerender(
      <DebugPanel
        {...props}
        isLoading={false}
        onRetryRegeneration={onRetryRegeneration}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'common.core.retry' }));
    expect(onRetryRegeneration).toHaveBeenCalledTimes(1);

    rerender(
      <DebugPanel
        {...props}
        isLoading
        onRetryRegeneration={onRetryRegeneration}
      />,
    );
    expect(
      screen.queryByRole('button', { name: 'common.core.retry' }),
    ).not.toBeInTheDocument();
  });

  test('filters hidden variables and forwards visible system variable keys', () => {
    render(
      <DebugPanel
        isLoading
        items={[]}
        variableValues={{
          sys_user_nickname: 'Learner',
          hidden_topic: 'Concise',
          custom_topic: 'Testing',
        }}
        hiddenVariableKeys={['hidden_topic']}
        systemVariableKeys={['sys_user_nickname']}
        courseVariableKeys={['custom_topic']}
        shifuBid='shifu-1'
        onRegenerate={jest.fn()}
        onSubmitInteraction={jest.fn()}
      />,
    );

    expect(mockDebugVariablesPanel).toHaveBeenLastCalledWith(
      expect.objectContaining({
        variableValues: {
          sys_user_nickname: 'Learner',
          custom_topic: 'Testing',
        },
        systemVariableKeys: ['sys_user_nickname'],
        courseVariableKeys: ['custom_topic'],
      }),
    );
  });

  test('renders billing action for credit insufficient preview errors', () => {
    const items: ChatContentItem[] = [
      {
        element_bid: 'preview-business-error',
        generated_block_bid: 'preview-business-error',
        content: '积分余额不足，暂时无法继续调用，请先开通订阅或购买积分',
        type: ChatContentItemType.ERROR,
        business_code: 7101,
      },
    ];

    render(
      <DebugPanel
        isLoading={false}
        items={items}
        creditInsufficientAudience='teacher'
        shifuBid='shifu-1'
        onRegenerate={jest.fn()}
        onSubmitInteraction={jest.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.billing.alerts.actions.checkoutTopup',
      }),
    );

    expect(mockPush).toHaveBeenCalledWith('/admin/billing?tab=packages');
  });

  test('does not render a billing action for collaborator credit errors', () => {
    const items: ChatContentItem[] = [
      {
        element_bid: 'preview-business-error',
        generated_block_bid: 'preview-business-error',
        content: '课程负责人的积分不足，请联系课程负责人。',
        type: ChatContentItemType.ERROR,
        business_code: 7101,
      },
    ];

    render(
      <DebugPanel
        isLoading={false}
        items={items}
        creditInsufficientAudience='teacher-collaborator'
        shifuBid='shifu-1'
        onRegenerate={jest.fn()}
        onSubmitInteraction={jest.fn()}
      />,
    );

    expect(
      screen.getByText('课程负责人的积分不足，请联系课程负责人。'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'module.billing.alerts.actions.checkoutTopup',
      }),
    ).not.toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  test('shows later preview items immediately when debug preview typewriter is disabled', () => {
    const items: ChatContentItem[] = [
      {
        element_bid: 'text-1',
        generated_block_bid: '0',
        content: '第一段内容',
        type: ChatContentItemType.CONTENT,
        element_type: 'text',
        shouldUseTypewriter: true,
        is_final: true,
        is_speakable: true,
      },
      {
        element_bid: 'text-1-feedback',
        generated_block_bid: '0-feedback',
        parent_element_bid: 'text-1',
        parent_block_bid: 'text-1',
        type: ChatContentItemType.LIKE_STATUS,
      },
      {
        element_bid: 'text-2',
        generated_block_bid: '1',
        content: '第二段内容',
        type: ChatContentItemType.CONTENT,
        element_type: 'text',
        shouldUseTypewriter: false,
        is_final: true,
      },
    ];

    render(
      <DebugPanel
        isLoading={false}
        items={items}
        shifuBid='shifu-1'
        onRegenerate={jest.fn()}
        onSubmitInteraction={jest.fn()}
        onRequestElementAudio={jest.fn().mockResolvedValue(null)}
      />,
    );

    expect(screen.getByText('第一段内容')).toBeInTheDocument();
    expect(screen.getByText('第二段内容')).toBeInTheDocument();
    expect(screen.getByText('text-1')).toBeInTheDocument();
    expect(screen.queryByText('typing')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'finish-text-1' }),
    ).not.toBeInTheDocument();
  });

  test('shows the provided preview error message when preview is empty', () => {
    render(
      <DebugPanel
        isLoading={false}
        errorMessage='Preview parameters are incomplete.'
        items={[]}
        shifuBid='shifu-1'
        onRegenerate={jest.fn()}
        onSubmitInteraction={jest.fn()}
      />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Preview parameters are incomplete.',
    );
    expect(
      screen.queryByText('module.shifu.previewArea.empty'),
    ).not.toBeInTheDocument();
  });

  test('copies preview content with hover guidance and copied button feedback', async () => {
    mockCopyText.mockResolvedValue(undefined);
    const items: ChatContentItem[] = [
      {
        element_bid: 'text-1',
        generated_block_bid: '0',
        content: 'First paragraph content',
        type: ChatContentItemType.CONTENT,
        element_type: 'text',
        is_final: true,
      },
    ];

    render(
      <DebugPanel
        isLoading={false}
        items={items}
        shifuBid='shifu-1'
        onRegenerate={jest.fn()}
        onSubmitInteraction={jest.fn()}
      />,
    );

    const copyButton = screen.getByRole('button', {
      name: 'module.shifu.previewArea.copy',
    });

    expect(screen.getByRole('tooltip')).toHaveTextContent(
      'module.shifu.previewArea.copyTooltip',
    );

    fireEvent.click(copyButton);

    await waitFor(() => {
      expect(mockCopyText).toHaveBeenCalledWith(
        '!===' + '\nFirst paragraph content\n' + '!===',
      );
    });
    expect(
      screen.getByRole('button', {
        name: 'module.shifu.previewArea.copied',
      }),
    ).toBeInTheDocument();
  });

  test('builds stable preview item keys from business ids and falls back to idx only when needed', () => {
    expect(
      resolveDebugItemKey({
        element_bid: 'text-1',
        generated_block_bid: 'block-1',
        content: '第一段内容',
        type: ChatContentItemType.CONTENT,
      } as ChatContentItem),
    ).toBe('content:text-1');

    expect(
      resolveDebugItemKey({
        element_bid: 'feedback-1',
        generated_block_bid: 'feedback-block-1',
        parent_element_bid: 'text-1',
        parent_block_bid: 'block-1',
        type: ChatContentItemType.LIKE_STATUS,
      } as ChatContentItem),
    ).toBe('like:feedback-1');

    expect(
      resolveDebugItemKey({
        generated_block_bid: 'preview-business-error',
        content: 'error',
        type: ChatContentItemType.ERROR,
      } as ChatContentItem),
    ).toBe('error:preview-business-error');

    expect(
      resolveDebugItemKey({
        element_bid: 'interaction-1',
        generated_block_bid: 'block-2',
        content: '请选择',
        type: ChatContentItemType.INTERACTION,
      } as ChatContentItem),
    ).toBe('interaction:interaction-1');

    expect(
      resolveDebugItemKey(
        {
          content: 'streaming text that should not become the key',
          type: ChatContentItemType.CONTENT,
        } as ChatContentItem,
        7,
      ),
    ).toBe('content:idx-7');

    expect(
      resolveDebugItemKey(
        {
          content: '',
          type: ChatContentItemType.ERROR,
        } as ChatContentItem,
        3,
      ),
    ).toBe('error:idx-3');
  });

  test('uses a dedicated preview content render key when typewriter state changes', () => {
    const items: ChatContentItem[] = [
      {
        element_bid: 'text-1',
        generated_block_bid: 'block-1',
        content: '第一段内容',
        type: ChatContentItemType.CONTENT,
        element_type: 'text',
        shouldUseTypewriter: true,
        is_final: false,
      },
    ];

    const { rerender } = render(
      <DebugPanel
        isLoading={false}
        items={items}
        shifuBid='shifu-1'
        onRegenerate={jest.fn()}
        onSubmitInteraction={jest.fn()}
      />,
    );

    expect(screen.getByTestId('text-1')).toHaveAttribute(
      'data-content-render-key',
      'preview:content:text-1:text:typing',
    );

    rerender(
      <DebugPanel
        isLoading={false}
        items={[
          {
            ...items[0],
            is_final: true,
            shouldUseTypewriter: false,
          },
        ]}
        shifuBid='shifu-1'
        onRegenerate={jest.fn()}
        onSubmitInteraction={jest.fn()}
      />,
    );

    expect(screen.getByTestId('text-1')).toHaveAttribute(
      'data-content-render-key',
      'preview:content:text-1:text:static',
    );
  });

  test('shows both actions for text without a helper and forwards its element anchor', async () => {
    const onRegenerate = jest.fn();
    const onRequestElementAudio = jest.fn().mockResolvedValue(null);
    const items: ChatContentItem[] = [
      {
        element_bid: 'text-1',
        generated_block_bid: '0',
        content: 'Private lesson text with https://private.example/secret',
        type: ChatContentItemType.CONTENT,
        element_type: 'text',
        is_final: true,
      },
    ];
    const props = {
      isLoading: false,
      items,
      shifuBid: 'shifu-1',
      onRegenerate,
      onSubmitInteraction: jest.fn(),
      onRequestElementAudio,
      showRegenerateAction: true,
    };
    const { rerender } = render(<DebugPanel {...props} />);
    expect(mockTrackEvent).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'regenerate-text-1' }));
    expect(onRegenerate).toHaveBeenCalledWith('text-1');
    const audioButton = within(screen.getByTestId('actions-text-1')).getByRole(
      'button',
      { name: 'audio' },
    );
    expect(audioButton).toBeEnabled();
    fireEvent.click(audioButton);
    await waitFor(() =>
      expect(onRequestElementAudio).toHaveBeenCalledWith({
        shifuBid: 'shifu-1',
        elementBid: 'text-1',
        text: items[0].content,
      }),
    );
    expect(mockTrackEvent.mock.calls).toEqual([
      ['teacher_debug_tts_requested', { shifu_bid: 'shifu-1' }],
    ]);
    expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toMatch(
      /Private|private[.]example|text-1|element_bid|generated_block_bid|url|prompt|error/i,
    );
    rerender(<DebugPanel {...props} />);
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    fireEvent.click(audioButton);
    expect(mockTrackEvent).toHaveBeenCalledTimes(2);
    expect(onRequestElementAudio).toHaveBeenCalledTimes(2);
  });

  test('renders one action row per element when a helper refers to a shared generated block', () => {
    const onRegenerate = jest.fn();
    const onRequestElementAudio = jest.fn().mockResolvedValue(null);
    render(
      <DebugPanel
        isLoading={false}
        items={[
          {
            element_bid: 'text-1',
            generated_block_bid: '0',
            content: 'First paragraph',
            type: ChatContentItemType.CONTENT,
            element_type: 'text',
            is_final: true,
          },
          {
            element_bid: 'html-1',
            generated_block_bid: '0',
            content: '<div>rich block</div>',
            type: ChatContentItemType.CONTENT,
            element_type: 'html',
            is_final: true,
            audioTracks: [{ position: 0, audioUrl: '/cached.mp3' }],
          },
          {
            element_bid: 'feedback-1',
            generated_block_bid: 'feedback-1',
            parent_element_bid: '',
            parent_block_bid: '0',
            type: ChatContentItemType.LIKE_STATUS,
          },
        ]}
        shifuBid='shifu-1'
        onRegenerate={onRegenerate}
        onSubmitInteraction={jest.fn()}
        onRequestElementAudio={onRequestElementAudio}
        showRegenerateAction
      />,
    );
    expect(screen.getAllByTestId('interaction-block')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: 'regenerate-text-1' }));
    expect(onRegenerate).toHaveBeenCalledWith('text-1');
    const regenerate = screen.getByRole('button', {
      name: 'regenerate-html-1',
    });
    const audio = within(screen.getByTestId('actions-html-1')).getByRole(
      'button',
      { name: 'audio' },
    );
    expect(regenerate).toBeDisabled();
    expect(audio).toBeDisabled();
    fireEvent.click(regenerate);
    fireEvent.click(audio);
    expect(onRegenerate).toHaveBeenCalledTimes(1);
    expect(onRequestElementAudio).not.toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });

  test.each([
    'interaction',
    'html',
    'code',
    'image',
    'mermaid',
    'svg',
  ] as const)(
    'shows disabled actions for a non-text %s element',
    elementType => {
      const onRegenerate = jest.fn();
      const onRequestElementAudio = jest.fn().mockResolvedValue(null);
      render(
        <DebugPanel
          isLoading={false}
          items={[
            {
              element_bid: 'non-text-1',
              generated_block_bid: 'turn-1',
              content: 'Non-text content',
              type:
                elementType === 'interaction'
                  ? ChatContentItemType.INTERACTION
                  : ChatContentItemType.CONTENT,
              element_type: elementType,
              is_final: true,
              is_speakable: true,
            },
          ]}
          shifuBid='shifu-1'
          onRegenerate={onRegenerate}
          onSubmitInteraction={jest.fn()}
          onRequestElementAudio={onRequestElementAudio}
          showRegenerateAction
        />,
      );
      const regenerate = screen.getByRole('button', {
        name: 'regenerate-non-text-1',
      });
      const audio = within(screen.getByTestId('actions-non-text-1')).getByRole(
        'button',
        { name: 'audio' },
      );
      expect(regenerate).toBeDisabled();
      expect(audio).toBeDisabled();
      fireEvent.click(regenerate);
      fireEvent.click(audio);
      expect(onRegenerate).not.toHaveBeenCalled();
      expect(onRequestElementAudio).not.toHaveBeenCalled();
      expect(mockTrackEvent).not.toHaveBeenCalled();
    },
  );

  test.each([
    {
      name: 'readonly course',
      showRegenerateAction: false,
      isLoading: false,
      generatedBlockBid: 'turn-1',
    },
    {
      name: 'running generation',
      showRegenerateAction: true,
      isLoading: true,
      generatedBlockBid: 'turn-1',
    },
    {
      name: 'missing generated anchor',
      showRegenerateAction: true,
      isLoading: false,
      generatedBlockBid: undefined,
    },
  ])(
    'disables regeneration for $name while retaining text audio',
    ({ showRegenerateAction, isLoading, generatedBlockBid }) => {
      const onRegenerate = jest.fn();
      render(
        <DebugPanel
          isLoading={isLoading}
          items={[
            {
              element_bid: 'text-1',
              generated_block_bid: generatedBlockBid,
              content: 'Ready text',
              type: ChatContentItemType.CONTENT,
              element_type: 'text',
              is_final: true,
            },
          ]}
          shifuBid='shifu-1'
          onRegenerate={onRegenerate}
          onSubmitInteraction={jest.fn()}
          onRequestElementAudio={jest.fn().mockResolvedValue(null)}
          showRegenerateAction={showRegenerateAction}
        />,
      );
      const regenerate = screen.getByRole('button', {
        name: 'regenerate-text-1',
      });
      expect(regenerate).toBeDisabled();
      fireEvent.click(regenerate);
      expect(onRegenerate).not.toHaveBeenCalled();
      expect(
        within(screen.getByTestId('actions-text-1')).getByRole('button', {
          name: 'audio',
        }),
      ).toBeEnabled();
      expect(mockTrackEvent).not.toHaveBeenCalled();
    },
  );

  test.each([
    {
      name: 'non-speakable text',
      isSpeakable: false,
      isFinal: true,
      content: 'Ready text',
      ttsEnabled: true,
    },
    {
      name: 'streaming text',
      isSpeakable: true,
      isFinal: false,
      content: 'Partial text',
      ttsEnabled: true,
    },
    {
      name: 'empty text',
      isSpeakable: true,
      isFinal: true,
      content: '   ',
      ttsEnabled: true,
    },
    {
      name: 'course TTS disabled',
      isSpeakable: true,
      isFinal: true,
      content: 'Ready text',
      ttsEnabled: false,
    },
  ])(
    'disables TTS for $name without blocking regeneration',
    ({ isSpeakable, isFinal, content, ttsEnabled }) => {
      const onRequestElementAudio = jest.fn().mockResolvedValue(null);
      render(
        <DebugPanel
          isLoading={false}
          items={[
            {
              element_bid: 'text-1',
              generated_block_bid: 'turn-1',
              content,
              type: ChatContentItemType.CONTENT,
              element_type: 'text',
              is_final: isFinal,
              is_speakable: isSpeakable,
            },
          ]}
          shifuBid='shifu-1'
          onRegenerate={jest.fn()}
          onSubmitInteraction={jest.fn()}
          onRequestElementAudio={ttsEnabled ? onRequestElementAudio : undefined}
          showRegenerateAction
        />,
      );
      expect(
        screen.getByRole('button', { name: 'regenerate-text-1' }),
      ).toBeEnabled();
      const audio = within(screen.getByTestId('actions-text-1')).getByRole(
        'button',
        { name: 'audio' },
      );
      expect(audio).toBeDisabled();
      fireEvent.click(audio);
      expect(onRequestElementAudio).not.toHaveBeenCalled();
      expect(mockTrackEvent).not.toHaveBeenCalled();
    },
  );

  test('excludes helper rows, errors and loading placeholders from element actions', () => {
    render(
      <DebugPanel
        isLoading={false}
        items={[
          {
            element_bid: 'missing-parent-feedback',
            parent_element_bid: 'missing-parent',
            type: ChatContentItemType.LIKE_STATUS,
          },
          {
            element_bid: 'debug-error',
            content: 'Generation failed',
            type: ChatContentItemType.ERROR,
          },
          {
            element_bid: 'loading',
            generated_block_bid: 'loading',
            content: '',
            type: ChatContentItemType.CONTENT,
          },
          {
            element_bid: 'loading-text',
            generated_block_bid: 'loading',
            content: '',
            type: ChatContentItemType.CONTENT,
            element_type: 'text',
          },
        ]}
        shifuBid='shifu-1'
        onRegenerate={jest.fn()}
        onSubmitInteraction={jest.fn()}
        onRequestElementAudio={jest.fn().mockResolvedValue(null)}
        showRegenerateAction
      />,
    );
    expect(screen.queryByTestId('interaction-block')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'audio' }),
    ).not.toBeInTheDocument();
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });

  test.each(['synchronous', 'asynchronous'])(
    'keeps TTS available when tracking fails %s',
    async failureMode => {
      if (failureMode === 'synchronous') {
        mockTrackEvent.mockImplementation(() => {
          throw new Error('Tracking unavailable');
        });
      } else {
        mockTrackEvent.mockRejectedValue(new Error('Tracking unavailable'));
      }
      const onRequestElementAudio = jest.fn().mockResolvedValue(null);
      render(
        <DebugPanel
          isLoading={false}
          items={[
            {
              element_bid: 'text-1',
              generated_block_bid: 'turn-1',
              content: 'Ready text',
              type: ChatContentItemType.CONTENT,
              element_type: 'text',
              is_final: true,
            },
          ]}
          shifuBid='shifu-1'
          onRegenerate={jest.fn()}
          onSubmitInteraction={jest.fn()}
          onRequestElementAudio={onRequestElementAudio}
          showRegenerateAction
        />,
      );
      fireEvent.click(
        within(screen.getByTestId('actions-text-1')).getByRole('button', {
          name: 'audio',
        }),
      );
      await waitFor(() =>
        expect(onRequestElementAudio).toHaveBeenCalledTimes(1),
      );
      expect(onRequestElementAudio).toHaveBeenCalledWith({
        shifuBid: 'shifu-1',
        elementBid: 'text-1',
        text: 'Ready text',
      });
      expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    },
  );
});
