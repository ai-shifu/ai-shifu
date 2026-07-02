import { shouldHideReadModeContentForLoading } from './readModeRenderState';
import {
  projectListenModeItems,
  projectReadModeItems,
} from './chatUiModeProjection';
import { findLastVisibleLessonFeedbackElementBid } from './lessonFeedbackPromptState';
import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';

jest.mock('@/c-utils/lesson-feedback-interaction', () => ({
  isLessonFeedbackInteractionContent: (content?: string) =>
    content?.includes('sys_lesson_feedback_score') ?? false,
}));

describe('NewChatComp read mode loading gate', () => {
  it('keeps existing read content visible while a run is still loading', () => {
    expect(
      shouldHideReadModeContentForLoading({
        isLoading: true,
        hasReadModeItems: true,
        shouldShowReadModeStreamingDots: false,
      }),
    ).toBe(false);
  });

  it('shows streaming dots instead of a blank read view during an active run', () => {
    expect(
      shouldHideReadModeContentForLoading({
        isLoading: true,
        hasReadModeItems: false,
        shouldShowReadModeStreamingDots: true,
      }),
    ).toBe(false);
  });

  it('keeps the first-load blank state when there is no read content yet', () => {
    expect(
      shouldHideReadModeContentForLoading({
        isLoading: true,
        hasReadModeItems: false,
        shouldShowReadModeStreamingDots: false,
      }),
    ).toBe(true);
  });
});

describe('NewChatComp mode projections', () => {
  const askButtonMarkup =
    '<custom-button-after-content><span>Ask</span></custom-button-after-content>';

  it('adds mobile follow-up markup only in read mode projection', () => {
    const canonicalItems: ChatContentItem[] = [
      {
        element_bid: 'content-1',
        generated_block_bid: 'content-1',
        content: 'Lesson content',
        type: ChatContentItemType.CONTENT,
      },
      {
        element_bid: '',
        parent_element_bid: 'content-1',
        content: '',
        type: ChatContentItemType.LIKE_STATUS,
      },
    ];

    const readItems = projectReadModeItems({
      items: canonicalItems,
      askListByAnchorElementBid: {},
      mobileStyle: true,
      askButtonMarkup,
    });
    const listenItems = projectListenModeItems({
      items: readItems,
      askButtonMarkup,
    });

    expect(canonicalItems[0].content).toBe('Lesson content');
    expect(readItems[0].content).toContain('<custom-button-after-content>');
    expect(listenItems[0].content).toBe('Lesson content');
  });

  it('keeps desktop read projection free of mobile follow-up markup', () => {
    const canonicalItems: ChatContentItem[] = [
      {
        element_bid: 'content-1',
        generated_block_bid: 'content-1',
        content: 'Lesson content',
        isHistory: true,
        type: ChatContentItemType.CONTENT,
      },
    ];

    const readItems = projectReadModeItems({
      items: canonicalItems,
      askListByAnchorElementBid: {},
      mobileStyle: false,
      askButtonMarkup,
    });

    expect(readItems[0].content).toBe('Lesson content');
  });

  it('filters empty retired fallback elements from mode projections', () => {
    const canonicalItems: ChatContentItem[] = [
      {
        element_bid: 'retired-streaming-1',
        generated_block_bid: 'generated-1',
        content: '',
        is_renderable: false,
        type: ChatContentItemType.CONTENT,
      },
      {
        element_bid: 'visual-1',
        generated_block_bid: 'generated-1',
        content: '![figure](figure.png)',
        is_renderable: true,
        type: ChatContentItemType.CONTENT,
      },
    ];

    const readItems = projectReadModeItems({
      items: canonicalItems,
      askListByAnchorElementBid: {},
      mobileStyle: false,
      askButtonMarkup,
    });
    const listenItems = projectListenModeItems({
      items: canonicalItems,
      askButtonMarkup,
    });

    expect(readItems.map(item => item.element_bid)).toEqual(['visual-1']);
    expect(listenItems.map(item => item.element_bid)).toEqual(['visual-1']);
  });

  it('filters helper rows attached to empty retired fallback elements', () => {
    const canonicalItems: ChatContentItem[] = [
      {
        element_bid: 'retired-streaming-1',
        generated_block_bid: 'generated-1',
        content: '',
        is_renderable: false,
        type: ChatContentItemType.CONTENT,
      },
      {
        element_bid: '',
        parent_element_bid: 'retired-streaming-1',
        content: '',
        type: ChatContentItemType.LIKE_STATUS,
      },
      {
        element_bid: 'ask-1',
        parent_element_bid: 'retired-streaming-1',
        content: '',
        type: ChatContentItemType.ASK,
      },
      {
        element_bid: 'visual-1',
        generated_block_bid: 'generated-1',
        content: '![figure](figure.png)',
        is_renderable: true,
        type: ChatContentItemType.CONTENT,
      },
    ];

    const readItems = projectReadModeItems({
      items: canonicalItems,
      askListByAnchorElementBid: {},
      mobileStyle: false,
      askButtonMarkup,
    });
    const listenItems = projectListenModeItems({
      items: canonicalItems,
      askButtonMarkup,
    });

    expect(readItems.map(item => item.element_bid)).toEqual(['visual-1']);
    expect(listenItems.map(item => item.element_bid)).toEqual(['visual-1']);
  });

  it('keeps selected interaction blocks in listen mode projection', () => {
    const canonicalItems: ChatContentItem[] = [
      {
        element_bid: 'retired-streaming-1',
        generated_block_bid: 'generated-1',
        content: '',
        is_renderable: false,
        type: ChatContentItemType.CONTENT,
      },
      {
        element_bid: 'interaction-1',
        parent_element_bid: 'retired-streaming-1',
        generated_block_bid: 'interaction-1',
        content: '?[%{{knowledge_level}} 完全不了解 | 略知一二 | 比较熟悉]',
        is_renderable: false,
        type: ChatContentItemType.INTERACTION,
        user_input: '比较熟悉',
        readonly: true,
      },
      {
        element_bid: 'visual-1',
        generated_block_bid: 'generated-1',
        content: '![figure](figure.png)',
        is_renderable: true,
        type: ChatContentItemType.CONTENT,
      },
    ];

    const listenItems = projectListenModeItems({
      items: canonicalItems,
      askButtonMarkup,
    });

    expect(listenItems.map(item => item.element_bid)).toEqual([
      'interaction-1',
      'visual-1',
    ]);
    expect(listenItems[0]).toEqual(
      expect.objectContaining({
        element_bid: 'interaction-1',
        type: ChatContentItemType.INTERACTION,
        user_input: '比较熟悉',
        readonly: true,
      }),
    );
  });

  it('normalizes finalized listen content as read history before projecting buttons', () => {
    const canonicalItems: ChatContentItem[] = [
      {
        element_bid: 'content-1',
        generated_block_bid: 'generated-1',
        content: 'Finished text',
        shouldRenderAsHistoryInReadMode: true,
        shouldUseTypewriter: true,
        type: ChatContentItemType.CONTENT,
      },
    ];

    const readItems = projectReadModeItems({
      items: canonicalItems,
      askListByAnchorElementBid: {},
      mobileStyle: false,
      askButtonMarkup,
    });

    expect(readItems[0]).toEqual(
      expect.objectContaining({
        isHistory: true,
        shouldUseTypewriter: false,
      }),
    );
  });

  it('tracks the latest visible lesson feedback interaction anchor', () => {
    expect(
      findLastVisibleLessonFeedbackElementBid([
        {
          element_bid: 'feedback-old',
          content: '%{{sys_lesson_feedback_score}}1|2|3|4|5|...comment',
          type: ChatContentItemType.INTERACTION,
        },
        {
          element_bid: 'content-1',
          content: 'Lesson content',
          type: ChatContentItemType.CONTENT,
        },
        {
          element_bid: 'feedback-new',
          content: '%{{sys_lesson_feedback_score}}1|2|3|4|5|...comment',
          type: ChatContentItemType.INTERACTION,
        },
      ]),
    ).toBe('feedback-new');
  });
});
