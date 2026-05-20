import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import LessonPreview from './LessonPreview';
import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';

const mockPush = jest.fn();

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
    enableStreamingTypewriter,
    onTypeFinished,
  }: {
    item: ChatContentItem;
    blockBid: string;
    enableStreamingTypewriter?: boolean;
    onTypeFinished?: (blockBid: string, content: string) => void;
  }) => (
    <div data-testid={item.element_bid}>
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
  default: ({ element_bid }: { element_bid?: string }) => (
    <div data-testid='interaction-block'>{element_bid}</div>
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
  });

  test('renders billing action for credit insufficient preview errors', () => {
    const items: ChatContentItem[] = [
      {
        element_bid: 'preview-business-error',
        generated_block_bid: 'preview-business-error',
        content: '积分余额不足，暂时无法继续调用，请先充值或开通订阅',
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

  test('reveals speaker helper row and later preview items after typewriter finishes', () => {
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
    expect(screen.queryByText('第二段内容')).not.toBeInTheDocument();
    expect(screen.queryByText('text-1')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'finish-text-1' }));

    expect(screen.getByText('第二段内容')).toBeInTheDocument();
    expect(screen.getByText('text-1')).toBeInTheDocument();
  });
});
