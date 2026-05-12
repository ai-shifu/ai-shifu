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
  default: ({ item }: { item: ChatContentItem }) => <div>{item.content}</div>,
}));

jest.mock('@/c-components/ChatUi/InteractionBlock', () => ({
  __esModule: true,
  default: () => null,
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
});
