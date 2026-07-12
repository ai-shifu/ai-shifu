import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import {
  isLessonPdfContentReady,
  shouldExcludeLessonPdfInteraction,
} from './lessonPdfState';

jest.mock('@/c-utils/lesson-feedback-interaction', () => ({
  isLessonFeedbackInteractionContent: (content?: string) =>
    content?.includes('sys_lesson_feedback_score') ?? false,
}));

jest.mock('@/c-utils/system-interaction', () => ({
  isSystemInteractionContent: (content?: string) =>
    /_sys_(next_chapter|pay|login)/.test(content ?? ''),
}));

const textItem: ChatContentItem = {
  type: ChatContentItemType.CONTENT,
  element_bid: 'text-1',
  element_type: 'text',
  content: 'Complete lesson content',
  is_final: true,
  shouldUseTypewriter: true,
};

const readyOptions = {
  courseName: 'One-person Company',
  lessonTitle: 'Lesson Two',
  lessonStatus: 'completed',
  isSlideMode: false,
  isLoading: false,
  isOutputInProgress: false,
  hasGenerationError: false,
  currentStreamingElementBid: '',
  readModeItems: [textItem],
  visibleReadModeItems: [textItem],
  readModeTypewriterCache: {
    'text-1': {
      content: 'Complete lesson content',
      isFinished: true,
    },
  },
};

describe('isLessonPdfContentReady', () => {
  it('allows the PDF entry only after the completed lesson is fully rendered', () => {
    expect(isLessonPdfContentReady(readyOptions)).toBe(true);
  });

  it.each([
    ['course name', { courseName: '  ' }],
    ['lesson title', { lessonTitle: '' }],
    ['lesson status', { lessonStatus: 'in_progress' }],
    ['lesson loading', { isLoading: true }],
    ['main output', { isOutputInProgress: true }],
    ['generation error', { hasGenerationError: true }],
    ['streaming element', { currentStreamingElementBid: 'text-1' }],
  ])('blocks the PDF entry while %s is unsettled', (_label, overrides) => {
    expect(
      isLessonPdfContentReady({
        ...readyOptions,
        ...overrides,
      }),
    ).toBe(false);
  });

  it('allows slide modes before the read-mode typewriter has been mounted', () => {
    expect(
      isLessonPdfContentReady({
        ...readyOptions,
        isSlideMode: true,
        visibleReadModeItems: [],
        readModeTypewriterCache: {},
      }),
    ).toBe(true);
  });

  it('blocks the PDF entry until every read-mode item is visible', () => {
    expect(
      isLessonPdfContentReady({
        ...readyOptions,
        visibleReadModeItems: [],
      }),
    ).toBe(false);
  });

  it('blocks the PDF entry until the final typewriter content is finished', () => {
    expect(
      isLessonPdfContentReady({
        ...readyOptions,
        readModeTypewriterCache: {
          'text-1': {
            content: 'Complete lesson content',
            isFinished: false,
          },
        },
      }),
    ).toBe(false);
  });

  it('allows a completed lesson whose only body is a course interaction', () => {
    const interactionItem: ChatContentItem = {
      type: ChatContentItemType.INTERACTION,
      element_bid: 'interaction-1',
      content: '?[%{{knowledge_level}} Beginner | Advanced]',
      is_final: true,
    };

    expect(
      isLessonPdfContentReady({
        ...readyOptions,
        readModeItems: [interactionItem],
        visibleReadModeItems: [interactionItem],
        readModeTypewriterCache: {},
      }),
    ).toBe(true);
  });

  it.each([
    ['lesson feedback', '%{{sys_lesson_feedback_score}}1|2|3|4|5'],
    ['next lesson', '?[Continue//_sys_next_chapter]'],
    ['payment', '?[Buy//_sys_pay]'],
    ['login', '?[Log in//_sys_login]'],
  ])('does not treat a %s interaction as lesson body', (_label, content) => {
    const interactionItem: ChatContentItem = {
      type: ChatContentItemType.INTERACTION,
      element_bid: 'interaction-1',
      content,
      is_final: true,
    };

    expect(
      isLessonPdfContentReady({
        ...readyOptions,
        readModeItems: [interactionItem],
        visibleReadModeItems: [interactionItem],
        readModeTypewriterCache: {},
      }),
    ).toBe(false);
  });
});

describe('shouldExcludeLessonPdfInteraction', () => {
  it('keeps ordinary course interactions printable', () => {
    expect(
      shouldExcludeLessonPdfInteraction(
        '?[%{{knowledge_level}} 完全不了解 | 略知一二 | 比较熟悉]',
      ),
    ).toBe(false);
  });

  it.each([
    ['lesson feedback', '%{{sys_lesson_feedback_score}}1|2|3|4|5'],
    ['next lesson', '?[继续学习//_sys_next_chapter]'],
    ['payment', '?[购买课程//_sys_pay]'],
    ['login', '?[登录//_sys_login]'],
  ])('excludes the %s interaction', (_label, content) => {
    expect(shouldExcludeLessonPdfInteraction(content)).toBe(true);
  });
});
