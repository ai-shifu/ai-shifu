import React from 'react';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppContext } from '../app-context';
import { LessonConversation } from './LessonConversation';
import { useAskStateStore } from './use-ask-state-store';
import { ChatContentItemType } from '@/types/chat-ui';

jest.mock('@/hooks/use-lesson-reset-status', () => ({
  LESSON_RESET_LIMIT_REACHED_CODE: 4021,
  useLessonResetStatus: () => ({ phase: 'ready', setFailure: jest.fn() }),
}));

const mockUseChatLogicHook = jest.fn();
const mockCloseLabel = 'Close answer';
const mockLegacyLabel = 'Legacy ask';
const mockCourseAvatar = '';
const mockIsCurrentUserCourseOwner = false;
let mockLearningMode = 'read';
const mockLogoHorizontal = '';
const mockLogoWideUrl = '';
const mockOfficialSiteUrl = 'https://official.example.com';
const mockReadFeedbackElementBid = '';
const mockLessonPdfReady = false;
let mockLessonPdfPreparing = false;
const mockPrintLessonPdf = jest.fn();
const mockPlaceholderTrackEvent = jest.fn();
const mockPlaceholderCallbacks = new Map<string, (() => void) | undefined>();

type MockScrollControlProps = {
  ariaLabel: string;
  bottomOffset?: number;
  contentVersion?: unknown;
  endRef: React.RefObject<HTMLElement | null>;
  followNewContent?: boolean;
  pageScrollFallback?: string;
  placement?: string;
  portalTarget?: HTMLElement | null;
  position?: string;
  scrollThreshold?: number;
  viewportRef: React.RefObject<HTMLElement | null>;
  zIndex?: number;
};

const mockScrollToBottomControl = jest.fn(
  ({ ariaLabel }: MockScrollControlProps) => (
    <button
      type='button'
      data-testid='scroll-to-bottom-control'
      aria-label={ariaLabel}
    />
  ),
);
const mockIntersectionObserver = jest.fn(
  (
    callback: IntersectionObserverCallback,
    options?: IntersectionObserverInit,
  ) => {
    void callback;
    void options;
    return {
      disconnect: jest.fn(),
      observe: jest.fn(),
      takeRecords: jest.fn(),
      unobserve: jest.fn(),
    };
  },
);

Object.defineProperty(global, 'IntersectionObserver', {
  configurable: true,
  value: mockIntersectionObserver,
  writable: true,
});

jest.mock('react-i18next', () => {
  const chat = jest.requireActual<Record<string, string>>(
    '../../../../../../../i18n/zh-CN/modules/chat.json',
  );
  const translations: Record<string, string> = {
    'common.core.cancel': '取消',
    'common.core.ok': '确认',
    'common.core.scrollToBottom': '滚动到底部',
    'module.chat.ask': '追问',
    'module.chat.lessonUpdateRecommendRetake': chat.lessonUpdateRecommendRetake,
    'module.chat.lessonFeedbackSubmit': '提交',
    'module.chat.lessonPdfCourseQrLabel': '扫码进入课程，获得一对一讲解与答疑',
    'module.chat.lessonUpdateRetakeAccessibleLabel':
      chat.lessonUpdateRetakeAccessibleLabel,
    'module.lesson.reset.confirmContent': '重修会清空本节学习数据。确定重修？',
    'module.lesson.reset.confirmTitle': '确认重修',
    'module.billing.alerts.actions.checkoutTopup': '购买积分',
  };

  return {
    Trans: ({ i18nKey, components }: any) => {
      const text = translations[i18nKey] || i18nKey;
      const match = text.match(/^(.*)<action>(.*)<\/action>(.*)$/);
      if (!match) {
        return <>{text}</>;
      }

      return (
        <>
          {match[1]}
          {React.cloneElement(components.action, {}, match[2])}
          {match[3]}
        </>
      );
    },
    useTranslation: () => ({
      t: (key: string) => translations[key] || key,
    }),
  };
});

jest.mock('markdown-flow-ui/scroll', () => ({
  ScrollToBottomControl: (props: MockScrollControlProps) =>
    mockScrollToBottomControl(props),
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('zustand/react/shallow', () => ({
  useShallow: (selector: unknown) => selector,
}));

jest.mock('@/assets/learner/light/icon-ask.svg', () => ({
  __esModule: true,
  default: { src: '/ask.svg' },
}));

jest.mock('@/assets/logos/ai-shifu-logo-horizontal.png', () => ({
  __esModule: true,
  default: {
    src: '/ai-shifu-logo-horizontal.png',
    width: 488,
    height: 128,
  },
}));

jest.mock('@/app/c/[[...id]]/events', () => ({
  stopActiveLessonStream: jest.fn(),
}));

jest.mock('@/app/c/[[...id]]/components/chat/use-lesson-conversation', () => ({
  __esModule: true,
  default: (...args: unknown[]) => mockUseChatLogicHook(...args),
  ChatContentItemType: {
    ANSWER: 'answer',
    ASK: 'ask',
    CONTENT: 'content',
    ERROR: 'error',
    INTERACTION: 'interaction',
    LIKE_STATUS: 'like_status',
  },
}));

jest.mock(
  '@/app/c/[[...id]]/components/chat/use-lesson-conversation-scroll',
  () => ({
    useLessonConversationScroll: () => ({
      scrollToLesson: jest.fn(),
    }),
  }),
);

jest.mock('./listen-mode-utils', () => ({
  ...jest.requireActual('./listen-mode-utils'),
  getMissingListenModeAudioBlockBids: () => [],
  getPendingListenModeAudioBackfillElementBids: () => [],
}));

jest.mock('./lesson-feedback-prompt-state', () => ({
  findLastVisibleLessonFeedbackElementBid: () => mockReadFeedbackElementBid,
}));

jest.mock('./lesson-pdf-state', () => ({
  isLessonPdfContentReady: () => mockLessonPdfReady,
  shouldExcludeLessonPdfInteraction: () => false,
}));

jest.mock('./use-lesson-pdf-print', () => ({
  useLessonPdfPrint: () => ({
    isPreparing: mockLessonPdfPreparing,
    printLessonPdf: mockPrintLessonPdf,
  }),
}));

jest.mock('@/hooks/use-tracking', () => ({
  useTracking: () => ({
    trackEvent: mockPlaceholderTrackEvent,
    trackTrailProgress: jest.fn(),
  }),
}));

jest.mock('@/lib/shifu/shifu-runtime', () => ({
  shifu: {
    resetTools: {
      resetChapter: jest.fn(),
    },
  },
}));

jest.mock('@/store/env-store', () => ({
  useEnvStore: Object.assign(
    (selector: (state: any) => unknown) =>
      selector({
        courseId: 'shifu-1',
        logoHorizontal: mockLogoHorizontal,
        logoWideUrl: mockLogoWideUrl,
        officialSiteUrl: mockOfficialSiteUrl,
      }),
    {
      getState: () => ({
        courseId: 'shifu-1',
      }),
    },
  ),
}));

jest.mock('@/store', () => ({
  useUserStore: (selector: (state: any) => unknown) =>
    selector({
      refreshUserInfo: jest.fn(),
    }),
}));

jest.mock('@/store/use-course-store', () => ({
  useCourseStore: (selector: (state: any) => unknown) =>
    selector({
      courseAvatar: mockCourseAvatar,
      courseName: '测试课程',
      isCurrentUserCourseOwner: mockIsCurrentUserCourseOwner,
      courseTtsEnabled: true,
      openPayModal: jest.fn(),
      payModalResult: null,
      resetChapter: jest.fn(),
      resetedLessonId: null,
      resettingLessonId: null,
      updateLessonId: jest.fn(),
    }),
}));

jest.mock('@/store/use-system-store', () => ({
  useSystemStore: (selector: (state: any) => unknown) =>
    selector({
      previewMode: true,
      learningMode: mockLearningMode,
      updateLearningMode: jest.fn(),
    }),
}));

jest.mock('@/hooks/use-toast', () => ({
  fail: jest.fn(),
  toast: jest.fn(),
}));

jest.mock('@/hooks/use-exclusive-audio', () => ({
  __esModule: true,
  default: () => ({
    releaseExclusive: jest.fn(),
    requestExclusive: jest.fn(),
  }),
}));

jest.mock('@/components/ui/Dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <>{children}</> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => (
    <div role='dialog'>{children}</div>
  ),
  DialogDescription: ({ children }: { children: React.ReactNode }) => (
    <p>{children}</p>
  ),
  DialogFooter: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: { children: React.ReactNode }) => (
    <h2>{children}</h2>
  ),
}));

jest.mock(
  './AskBlock',
  () =>
    function MockAskBlock(props: any) {
      return (
        <section
          data-testid={`ask-${props.element_bid}`}
          data-inline={String(props.inlineReading)}
          data-expanded={String(props.isExpanded)}
          data-print={String(props.printMode)}
          data-readonly={String(props.readonlyHistory)}
        >
          {props.isExpanded && (
            <button onClick={props.onToggleAskExpanded}>
              {mockCloseLabel}
            </button>
          )}
        </section>
      );
    },
);

jest.mock('./use-reading-follow-up-point', () => ({
  useReadingFollowUpPoint: ({ enabled }: { enabled: boolean }) => {
    const [anchor, setAnchor] = React.useState('content-1');
    return {
      anchorElementBid: enabled ? anchor : null,
      selectAnchor: setAnchor,
    };
  },
}));
jest.mock(
  './ContentBlock',
  () =>
    function MockContentBlock({
      item,
      contentLanguage,
      contentRenderKey,
      enableStreamingTypewriter,
      onPlaceholderAccepted,
    }: {
      item: { content?: string; element_bid?: string };
      contentLanguage?: string;
      contentRenderKey?: string;
      enableStreamingTypewriter?: boolean;
      onPlaceholderAccepted?: () => void;
    }) {
      mockPlaceholderCallbacks.set(
        item.element_bid || '',
        onPlaceholderAccepted,
      );
      return (
        <div
          data-testid={`content-block-${item.element_bid || 'item'}`}
          data-content-language={contentLanguage}
          data-content-render-key={contentRenderKey}
          data-typewriter={String(Boolean(enableStreamingTypewriter))}
        >
          {item.content}
        </div>
      );
    },
);
jest.mock(
  './InteractionBlock',
  () =>
    function MockInteractionBlock({
      disableAskButton,
    }: {
      disableAskButton?: boolean;
    }) {
      return disableAskButton ? (
        <div />
      ) : (
        <button data-testid='legacy-ask'>{mockLegacyLabel}</button>
      );
    },
);
jest.mock(
  './MobileInteractionBlock',
  () =>
    function MockMobileInteractionBlock() {
      return <div />;
    },
);
jest.mock(
  './LessonFeedbackInteraction',
  () =>
    function MockLessonFeedbackInteraction() {
      return <div />;
    },
);
jest.mock(
  './ListenModeSlideRenderer',
  () =>
    function MockListenModeSlideRenderer({
      titleLanguage,
      contentLanguage,
    }: {
      titleLanguage?: string;
      contentLanguage?: string;
    }) {
      return (
        <div
          data-testid='listen-mode-renderer'
          data-title-language={titleLanguage}
          data-content-language={contentLanguage}
        />
      );
    },
);
jest.mock(
  './LoadingBar',
  () =>
    function MockLoadingBar() {
      return <div />;
    },
);
jest.mock(
  './StreamingLoadingDotsBar',
  () =>
    function MockStreamingLoadingDotsBar() {
      return <div />;
    },
);
jest.mock(
  './LessonPdfPreparingOverlay',
  () =>
    function MockLessonPdfPreparingOverlay() {
      return <div data-testid='lesson-pdf-preparing-overlay' />;
    },
);
jest.mock('@/components/audio/AudioPlayer', () => ({
  AudioPlayer: function MockAudioPlayer() {
    return <div />;
  },
}));

const mockEnsureAsk = jest.fn();
const makeContent = (
  element_bid: string,
  extra: Record<string, unknown> = {},
) => ({
  element_bid,
  type: ChatContentItemType.CONTENT,
  element_type: 'text',
  content: `Lesson ${element_bid}`,
  isHistory: true,
  is_renderable: false,
  ...extra,
});
const makeActions = (parent_element_bid: string) => ({
  element_bid: '',
  parent_element_bid,
  content: '',
  type: ChatContentItemType.LIKE_STATUS,
});
const makeAsk = (parent_element_bid: string, history = false) => ({
  element_bid: `ask-${parent_element_bid}`,
  parent_element_bid,
  content: '',
  type: ChatContentItemType.ASK,
  isAskExpanded: false,
  ask_list: history
    ? [
        { element_bid: 'question-1', type: 'ask', content: 'Earlier question' },
        { element_bid: 'answer-1', type: 'answer', content: 'Earlier answer' },
      ]
    : [],
});

function configure(items: Array<Record<string, unknown>>) {
  mockUseChatLogicHook.mockReturnValue({
    currentStreamingElementBid: '',
    currentTypewriterElementBid: '',
    isLoading: false,
    isOutputInProgress: false,
    items,
    lessonFeedbackPopup: {
      open: false,
      onClose: jest.fn(),
      onSubmit: jest.fn(),
    },
    onRefresh: jest.fn(),
    onSend: jest.fn(),
    reGenerateConfirm: {
      open: false,
      onCancel: jest.fn(),
      onConfirm: jest.fn(),
    },
    requestAudioForBlock: jest.fn(),
    toggleAskExpanded: mockEnsureAsk,
  });
}

function renderConversation({
  mobile = false,
  mode = 'text',
  items = [],
}: {
  mobile?: boolean;
  mode?: 'text' | 'live_voice' | 'disabled';
  items?: Array<Record<string, unknown>>;
} = {}) {
  configure(items);
  return render(
    <AppContext.Provider
      value={{
        frameLayout: 1,
        isLoggedIn: true,
        mobileStyle: mobile,
        theme: 'light',
        userInfo: null,
      }}
    >
      <LessonConversation
        chapterId='chapter-1'
        chapterUpdate={jest.fn()}
        getNextLessonId={jest.fn()}
        lessonId='lesson-1'
        lessonTitle='Lesson'
        lessonUpdate={jest.fn()}
        onGoChapter={jest.fn()}
        onPurchased={jest.fn()}
        updateSelectedLesson={jest.fn()}
        followUpMode={mode}
      />
    </AppContext.Provider>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  jest.spyOn(window, 'requestAnimationFrame').mockReturnValue(1);
  mockLearningMode = 'read';
  mockLessonPdfPreparing = false;
  useAskStateStore.getState().clearLessonScope();
  Object.defineProperty(document, 'visibilityState', {
    value: 'visible',
    configurable: true,
  });
});

afterEach(() => {
  jest.restoreAllMocks();
});

test('reading entries exist only after finalized real course content, with no legacy duplicate ask controls', () => {
  const { container } = renderConversation({
    items: [
      makeContent('content-1'),
      makeActions('content-1'),
      makeAsk('content-1'),
      makeContent('content-2', { isHistory: false }),
      makeActions('content-2'),
      makeContent('unfinished', { isHistory: false }),
      makeContent('loading', { isHistory: false }),
      makeContent('hidden', { is_renderable: false, content: '' }),
      {
        element_bid: 'interaction-1',
        content: 'Choose',
        type: ChatContentItemType.INTERACTION,
      },
      makeActions('interaction-1'),
    ],
  });
  expect(
    [...container.querySelectorAll('[data-reading-follow-up-anchor]')].map(e =>
      e.getAttribute('data-reading-follow-up-anchor'),
    ),
  ).toEqual(['content-1', 'content-2']);
  expect(
    container.querySelectorAll('[data-reading-follow-up-marker]'),
  ).toHaveLength(2);
  expect(screen.queryByTestId('legacy-ask')).not.toBeInTheDocument();
  expect(screen.getByTestId('ask-content-1')).toHaveAttribute(
    'data-inline',
    'true',
  );
});

test('mobile reading removes embedded controls and opens the existing AskBlock inline at the selected end', async () => {
  const { container } = renderConversation({
    mobile: true,
    items: [
      makeContent('content-1', {
        content:
          'Mobile lesson<custom-button-after-content>Old ask</custom-button-after-content>',
      }),
      makeActions('content-1'),
      makeAsk('content-1'),
    ],
  });
  expect(
    screen.getByTestId('content-block-content-1').textContent,
  ).not.toContain('custom-button-after-content');
  expect(
    screen.getByTestId('content-block-content-1').textContent,
  ).not.toContain('Old ask');
  expect(
    container.querySelectorAll('[data-reading-follow-up-marker] button'),
  ).toHaveLength(1);
  await act(async () => {
    await userEvent.click(
      container.querySelector('[data-reading-follow-up-marker] button')!,
    );
  });
  expect(screen.getByTestId('ask-content-1')).toHaveAttribute(
    'data-inline',
    'true',
  );
  expect(screen.getByTestId('ask-content-1')).toHaveAttribute(
    'data-expanded',
    'true',
  );
  await act(async () => {
    await userEvent.click(screen.getByRole('button', { name: 'Close answer' }));
  });
  expect(screen.getByTestId('ask-content-1')).toHaveAttribute(
    'data-expanded',
    'false',
  );
});

test('collapsed persisted history reopens at its original reading boundary', async () => {
  renderConversation({
    items: [
      makeContent('content-1'),
      makeActions('content-1'),
      makeAsk('content-1', true),
    ],
  });
  expect(screen.getByTestId('ask-content-1')).toHaveAttribute(
    'data-expanded',
    'false',
  );
  const history = screen
    .getByTestId('ask-content-1')
    .parentElement!.querySelector('button')!;
  expect(history).toHaveTextContent('追问');
  expect(history).toHaveTextContent('1');
  await act(async () => {
    await userEvent.click(history);
  });
  expect(screen.getByTestId('ask-content-1')).toHaveAttribute(
    'data-expanded',
    'true',
  );
  expect(mockPlaceholderTrackEvent).toHaveBeenCalledWith(
    'learner_read_follow_up_opened',
    { surface: 'desktop', entry: 'history' },
  );
});

test.each(['disabled', 'print', 'listen'] as const)(
  'excludes reading entries in %s mode',
  state => {
    if (state === 'print') mockLessonPdfPreparing = true;
    if (state === 'listen') mockLearningMode = 'listen';
    const { container } = renderConversation({
      mode: state === 'disabled' ? 'disabled' : 'text',
      items: [
        makeContent('content-1'),
        makeActions('content-1'),
        makeAsk('content-1'),
      ],
    });
    expect(
      container.querySelector('[data-reading-follow-up-marker] button'),
    ).toBeNull();
    if (state === 'listen')
      expect(screen.getByTestId('listen-mode-renderer')).toBeInTheDocument();
    if (state === 'print')
      expect(screen.getByTestId('ask-content-1')).toHaveAttribute(
        'data-inline',
        'false',
      );
  },
);

test('keyboard focus exposes any reading boundary and Enter opens its inline answer', async () => {
  const { container } = renderConversation({
    items: [
      makeContent('content-1'),
      makeActions('content-1'),
      makeAsk('content-1'),
      makeContent('content-2'),
      makeActions('content-2'),
      makeAsk('content-2'),
    ],
  });
  const buttons = container.querySelectorAll<HTMLButtonElement>(
    '[data-reading-follow-up-marker] button',
  );
  expect(buttons).toHaveLength(2);
  expect(buttons[0]).toHaveAttribute('tabindex', '0');
  expect(buttons[1]).toHaveAttribute('tabindex', '0');
  act(() => buttons[1].focus());
  expect(
    container.querySelectorAll('[data-reading-follow-up-active="true"]'),
  ).toHaveLength(1);
  expect(buttons[1].closest('[data-reading-follow-up-anchor]')).toHaveAttribute(
    'data-reading-follow-up-anchor',
    'content-2',
  );
  expect(buttons[1].parentElement).toHaveAttribute(
    'data-reading-follow-up-active',
    'true',
  );
  await act(async () => {
    await userEvent.keyboard('{Enter}');
  });
  expect(screen.getByTestId('ask-content-2')).toHaveAttribute(
    'data-expanded',
    'true',
  );
  expect(screen.getByTestId('ask-content-1')).toHaveAttribute(
    'data-expanded',
    'false',
  );
  expect(buttons[0]).toHaveAttribute('tabindex', '-1');
  expect(buttons[1]).toHaveAttribute('tabindex', '-1');
});

test('disabled follow-up keeps persisted answers mounted as readonly history', () => {
  renderConversation({
    mode: 'disabled',
    items: [
      makeContent('content-1'),
      makeActions('content-1'),
      makeAsk('content-1', true),
    ],
  });
  expect(screen.getByTestId('ask-content-1')).toHaveAttribute(
    'data-readonly',
    'true',
  );
  expect(screen.getByTestId('ask-content-1')).toHaveAttribute(
    'data-inline',
    'false',
  );
});

test('legacy history on an interaction remains readonly even though it is not a reading entry', () => {
  const { container } = renderConversation({
    items: [
      {
        element_bid: 'interaction-1',
        content: 'Choose',
        type: ChatContentItemType.INTERACTION,
      },
      makeActions('interaction-1'),
      makeAsk('interaction-1', true),
    ],
  });
  expect(container.querySelector('[data-reading-follow-up-anchor]')).toBeNull();
  expect(screen.getByTestId('ask-interaction-1')).toHaveAttribute(
    'data-readonly',
    'true',
  );
  expect(screen.getByTestId('ask-interaction-1')).toHaveAttribute(
    'data-inline',
    'false',
  );
});
