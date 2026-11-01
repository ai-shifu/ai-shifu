import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import DebugPanel from './DebugPanel';
import { resolveDebugItemKey } from './DebugPanel';
import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';

const mockPush = jest.fn();
const mockCopyText = jest.fn();
const mockDebugVariablesPanel = jest.fn();

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
    extraActions,
  }: {
    element_bid?: string;
    showGenerateBtn?: boolean;
    onRefresh?: (elementBid: string) => void;
    extraActions?: React.ReactNode;
  }) => (
    <div data-testid='interaction-block'>
      <span>{element_bid}</span>
      {showGenerateBtn ? (
        <button
          type='button'
          aria-label={`regenerate-${element_bid}`}
          onClick={() => onRefresh?.(element_bid || '')}
        />
      ) : null}
      {extraActions}
    </div>
  ),
}));

jest.mock('@/components/audio/AudioPlayer', () => ({
  __esModule: true,
  AudioPlayer: ({
    onRequestAudio,
  }: {
    onRequestAudio?: () => Promise<unknown>;
  }) => (
    <button
      type='button'
      aria-label='audio'
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
        onSubmitInteraction={jest.fn()}
      />,
    );

    expect(screen.getByTestId('text-1')).toHaveAttribute(
      'data-content-render-key',
      'preview:content:text-1:text:static',
    );
  });

  test('removes content regeneration and retry controls while preserving text audio', async () => {
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
          {
            element_bid: 'html-1',
            generated_block_bid: 'turn-1',
            content: '<div>Rich content</div>',
            type: ChatContentItemType.CONTENT,
            element_type: 'html',
            is_final: true,
          },
          {
            element_bid: 'feedback-1',
            parent_block_bid: 'turn-1',
            type: ChatContentItemType.LIKE_STATUS,
          },
          {
            element_bid: 'interaction-1',
            generated_block_bid: 'turn-2',
            type: ChatContentItemType.INTERACTION,
            content: 'Choose an answer',
          },
        ]}
        shifuBid='shifu-1'
        onSubmitInteraction={jest.fn()}
        onRequestElementAudio={onRequestElementAudio}
      />,
    );
    expect(
      screen.queryByRole('button', { name: /^regenerate-/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'common.core.retry' }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'audio' })).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'audio' }));
    await waitFor(() =>
      expect(onRequestElementAudio).toHaveBeenCalledWith({
        shifuBid: 'shifu-1',
        elementBid: 'text-1',
        text: 'Ready text',
      }),
    );
    expect(
      screen.getAllByRole('button', { name: 'module.shifu.previewArea.copy' }),
    ).toHaveLength(2);
  });

  test.each(['empty', 'error'] as const)(
    'does not offer regeneration retry in the %s state',
    state => {
      render(
        <DebugPanel
          isLoading={false}
          items={
            state === 'error'
              ? [
                  {
                    element_bid: 'debug-error',
                    content: 'Debug failed',
                    type: ChatContentItemType.ERROR,
                  },
                ]
              : []
          }
          shifuBid='shifu-1'
          onSubmitInteraction={jest.fn()}
        />,
      );
      expect(
        screen.queryByRole('button', { name: 'common.core.retry' }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: /^regenerate-/ }),
      ).not.toBeInTheDocument();
      if (state === 'empty')
        expect(
          screen.getByText('module.shifu.previewArea.empty'),
        ).toBeInTheDocument();
      else expect(screen.getByText('Debug failed')).toBeInTheDocument();
    },
  );

  test('retains TTS course and text eligibility without exposing regeneration', () => {
    render(
      <DebugPanel
        isLoading={false}
        items={[
          {
            element_bid: 'text-1',
            generated_block_bid: 'turn-1',
            content: 'Text',
            type: ChatContentItemType.CONTENT,
            element_type: 'text',
          },
          {
            element_bid: 'feedback-1',
            parent_element_bid: 'text-1',
            type: ChatContentItemType.LIKE_STATUS,
          },
        ]}
        shifuBid='shifu-1'
        onSubmitInteraction={jest.fn()}
      />,
    );
    expect(
      screen.queryByRole('button', { name: 'audio' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId('interaction-block')).not.toBeInTheDocument();
  });
});
