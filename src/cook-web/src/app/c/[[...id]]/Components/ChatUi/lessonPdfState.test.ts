import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import { isLessonPdfContentReady } from './lessonPdfState';

const textItem: ChatContentItem = {
  type: ChatContentItemType.CONTENT,
  element_bid: 'text-1',
  element_type: 'text',
  content: 'Complete lesson content',
  is_final: true,
  shouldUseTypewriter: true,
};

const readyOptions = {
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
    ['lesson status', { lessonStatus: 'in_progress' }],
    ['lesson loading', { isLoading: true }],
    ['main output', { isOutputInProgress: true }],
    ['generation error', { hasGenerationError: true }],
    ['streaming element', { currentStreamingElementBid: 'text-1' }],
    ['slide mode', { isSlideMode: true }],
  ])('blocks the PDF entry while %s is unsettled', (_label, overrides) => {
    expect(
      isLessonPdfContentReady({
        ...readyOptions,
        ...overrides,
      }),
    ).toBe(false);
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
});
