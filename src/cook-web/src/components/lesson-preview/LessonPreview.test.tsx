import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import LessonPreview from './LessonPreview';
import { resolveLessonPreviewItemKey } from './LessonPreview';
import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';

const mockPush = jest.fn();
const mockCopyText = jest.fn();

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

jest.mock('@/components/ui/UseAlert', () => ({
  useAlert: () => ({
    showAlert: jest.fn(),
  }),
}));

jest.mock('@/components/ui/tooltip', () => {
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

jest.mock('@/c-utils/textutils', () => {
  const actual = jest.requireActual('@/c-utils/textutils');
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

jest.mock('@/c-components/ChatUi/ContentBlock', () => ({
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

jest.mock('@/c-components/ChatUi/InteractionBlock', () => ({
  __esModule: true,
  default: ({
    element_bid,
    showGenerateBtn,
    onRefresh,
  }: {
    element_bid?: string;
    showGenerateBtn?: boolean;
    onRefresh?: (elementBid: string) => void;
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
    </div>
  ),
}));

jest.mock('@/components/audio/AudioPlayer', () => ({
  __esModule: true,
  AudioPlayer: () => null,
}));

jest.mock('./VariableList', () => ({
  __esModule: true,
  default: () => null,
}));

describe('LessonPreview billing action', () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockCopyText.mockReset();
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
      <LessonPreview
        loading={false}
        items={items}
        shifuBid='shifu-1'
        onRefresh={jest.fn()}
        onSend={jest.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.shifu.previewArea.goToBilling',
      }),
    );

    expect(mockPush).toHaveBeenCalledWith('/admin/billing?tab=packages');
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
      <LessonPreview
        loading={false}
        items={items}
        shifuBid='shifu-1'
        onRefresh={jest.fn()}
        onSend={jest.fn()}
        onRequestAudioForBlock={jest.fn().mockResolvedValue(null)}
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
      <LessonPreview
        loading={false}
        items={items}
        shifuBid='shifu-1'
        onRefresh={jest.fn()}
        onSend={jest.fn()}
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
      resolveLessonPreviewItemKey({
        element_bid: 'text-1',
        generated_block_bid: 'block-1',
        content: '第一段内容',
        type: ChatContentItemType.CONTENT,
      } as ChatContentItem),
    ).toBe('content:text-1');

    expect(
      resolveLessonPreviewItemKey({
        element_bid: 'feedback-1',
        generated_block_bid: 'feedback-block-1',
        parent_element_bid: 'text-1',
        parent_block_bid: 'block-1',
        type: ChatContentItemType.LIKE_STATUS,
      } as ChatContentItem),
    ).toBe('like:feedback-1');

    expect(
      resolveLessonPreviewItemKey({
        generated_block_bid: 'preview-business-error',
        content: 'error',
        type: ChatContentItemType.ERROR,
      } as ChatContentItem),
    ).toBe('error:preview-business-error');

    expect(
      resolveLessonPreviewItemKey({
        element_bid: 'interaction-1',
        generated_block_bid: 'block-2',
        content: '请选择',
        type: ChatContentItemType.INTERACTION,
      } as ChatContentItem),
    ).toBe('interaction:interaction-1');

    expect(
      resolveLessonPreviewItemKey(
        {
          content: 'streaming text that should not become the key',
          type: ChatContentItemType.CONTENT,
        } as ChatContentItem,
        7,
      ),
    ).toBe('content:idx-7');

    expect(
      resolveLessonPreviewItemKey(
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
      <LessonPreview
        loading={false}
        items={items}
        shifuBid='shifu-1'
        onRefresh={jest.fn()}
        onSend={jest.fn()}
      />,
    );

    expect(screen.getByTestId('text-1')).toHaveAttribute(
      'data-content-render-key',
      'preview:content:text-1:text:typing',
    );

    rerender(
      <LessonPreview
        loading={false}
        items={[
          {
            ...items[0],
            is_final: true,
            shouldUseTypewriter: false,
          },
        ]}
        shifuBid='shifu-1'
        onRefresh={jest.fn()}
        onSend={jest.fn()}
      />,
    );

    expect(screen.getByTestId('text-1')).toHaveAttribute(
      'data-content-render-key',
      'preview:content:text-1:text:static',
    );
  });

  test('routes preview regenerate from helper row to the parent content item', () => {
    const onRefresh = jest.fn();
    const items: ChatContentItem[] = [
      {
        element_bid: 'text-1',
        generated_block_bid: '0',
        content: '第一段内容',
        type: ChatContentItemType.CONTENT,
        element_type: 'text',
        is_final: true,
        is_speakable: true,
      },
      {
        element_bid: 'text-1-feedback',
        generated_block_bid: 'text-1-feedback',
        parent_element_bid: 'text-1',
        parent_block_bid: '0',
        type: ChatContentItemType.LIKE_STATUS,
      },
    ];

    render(
      <LessonPreview
        loading={false}
        items={items}
        shifuBid='shifu-1'
        onRefresh={onRefresh}
        onSend={jest.fn()}
        showGenerateBtn
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'regenerate-text-1' }));

    expect(onRefresh).toHaveBeenCalledWith('text-1');
  });

  test('prefers a text parent when generated block items include mixed element types', () => {
    const onRefresh = jest.fn();
    const items: ChatContentItem[] = [
      {
        element_bid: 'text-1',
        generated_block_bid: '0',
        content: '第一段内容',
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
      },
      {
        element_bid: 'feedback-1',
        generated_block_bid: 'feedback-1',
        parent_element_bid: '',
        parent_block_bid: '0',
        type: ChatContentItemType.LIKE_STATUS,
      },
    ];

    render(
      <LessonPreview
        loading={false}
        items={items}
        shifuBid='shifu-1'
        onRefresh={onRefresh}
        onSend={jest.fn()}
        showGenerateBtn
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'regenerate-text-1' }));

    expect(onRefresh).toHaveBeenCalledWith('text-1');
    expect(
      screen.queryByRole('button', { name: 'regenerate-html-1' }),
    ).not.toBeInTheDocument();
  });

  test('does not expose regenerate when the preview generate action is disabled', () => {
    const items: ChatContentItem[] = [
      {
        element_bid: 'text-1',
        generated_block_bid: '0',
        content: '第一段内容',
        type: ChatContentItemType.CONTENT,
        element_type: 'text',
        is_final: true,
        is_speakable: true,
      },
      {
        element_bid: 'text-1-feedback',
        generated_block_bid: 'text-1-feedback',
        parent_element_bid: 'text-1',
        parent_block_bid: '0',
        type: ChatContentItemType.LIKE_STATUS,
      },
    ];

    render(
      <LessonPreview
        loading={false}
        items={items}
        shifuBid='shifu-1'
        onRefresh={jest.fn()}
        onSend={jest.fn()}
      />,
    );

    expect(
      screen.queryByRole('button', { name: 'regenerate-text-1' }),
    ).not.toBeInTheDocument();
  });

  test('does not expose regenerate for helper rows without a valid parent item', () => {
    const items: ChatContentItem[] = [
      {
        element_bid: 'missing-parent-feedback',
        generated_block_bid: 'missing-parent-feedback',
        parent_element_bid: 'missing-parent',
        parent_block_bid: '9',
        type: ChatContentItemType.LIKE_STATUS,
      },
    ];

    render(
      <LessonPreview
        loading={false}
        items={items}
        shifuBid='shifu-1'
        onRefresh={jest.fn()}
        onSend={jest.fn()}
        showGenerateBtn
      />,
    );

    expect(screen.queryByTestId('interaction-block')).not.toBeInTheDocument();
  });

  test('does not expose regenerate for interaction parent blocks', () => {
    const items: ChatContentItem[] = [
      {
        element_bid: 'interaction-1',
        generated_block_bid: '2',
        content: '["完全不了解","略知一二"]',
        type: ChatContentItemType.INTERACTION,
        is_final: true,
      },
      {
        element_bid: 'interaction-1-feedback',
        generated_block_bid: 'interaction-1-feedback',
        parent_element_bid: 'interaction-1',
        parent_block_bid: '2',
        type: ChatContentItemType.LIKE_STATUS,
      },
    ];

    render(
      <LessonPreview
        loading={false}
        items={items}
        shifuBid='shifu-1'
        onRefresh={jest.fn()}
        onSend={jest.fn()}
        showGenerateBtn
      />,
    );

    expect(
      screen.queryByRole('button', { name: 'regenerate-interaction-1' }),
    ).not.toBeInTheDocument();
  });

  test('does not expose regenerate for non-text content blocks', () => {
    const items: ChatContentItem[] = [
      {
        element_bid: 'rich-1',
        generated_block_bid: '3',
        content: '<div>rich block</div>',
        type: ChatContentItemType.CONTENT,
        element_type: 'html',
        is_final: true,
      },
      {
        element_bid: 'rich-1-feedback',
        generated_block_bid: 'rich-1-feedback',
        parent_element_bid: 'rich-1',
        parent_block_bid: '3',
        type: ChatContentItemType.LIKE_STATUS,
      },
    ];

    render(
      <LessonPreview
        loading={false}
        items={items}
        shifuBid='shifu-1'
        onRefresh={jest.fn()}
        onSend={jest.fn()}
        showGenerateBtn
      />,
    );

    expect(
      screen.queryByRole('button', { name: 'regenerate-rich-1' }),
    ).not.toBeInTheDocument();
  });
});
