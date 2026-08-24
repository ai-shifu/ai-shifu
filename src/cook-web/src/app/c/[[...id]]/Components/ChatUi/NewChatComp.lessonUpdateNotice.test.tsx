import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppContext } from '../AppContext';
import { NewChatComponents } from './NewChatComp';
import LessonUpdateNotice from '../LessonUpdateNotice';

jest.mock('markdown-flow-ui/renderer', () => ({
  ScrollToBottomButton: ({ visible, onClick, ariaLabel }: any) =>
    visible ? (
      <button
        type='button'
        aria-label={ariaLabel}
        onClick={onClick}
      />
    ) : null,
  useScrollToBottom: () => ({
    showScrollToBottom: false,
    isAtBottom: true,
    followNewContent: true,
    scrollToBottom: jest.fn(),
    refresh: jest.fn(),
  }),
}));

const mockUseChatLogicHook = jest.fn();
let mockCourseAvatar = '';
let mockLearningMode = 'listen';
let mockLogoHorizontal = '';
let mockLogoWideUrl = '';
let mockOfficialSiteUrl = 'https://official.example.com';
let mockLessonPdfReady = false;
let mockLessonPdfPreparing = false;
const mockPrintLessonPdf = jest.fn();

jest.mock('react-i18next', () => {
  const translations: Record<string, string> = {
    'common.core.cancel': '取消',
    'common.core.ok': '确认',
    'module.chat.ask': '追问',
    'module.chat.lessonUpdateRecommendRetake':
      '本节课程已更新，建议<action>重修</action>',
    'module.chat.lessonFeedbackSubmit': '提交',
    'module.chat.scrollToBottom': '滚动到底部',
    'module.chat.lessonPdfCourseQrLabel': '扫码进入课程，获得一对一讲解与答疑',
    'module.chat.lessonUpdateRetakeAccessibleLabel': '重修本节课程',
    'module.chat.lessonUpdateRetakeAction': '重修',
    'module.lesson.reset.confirmContent': '重修会清空本节学习数据。确定重修？',
    'module.lesson.reset.confirmTitle': '确认重修',
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

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('zustand/react/shallow', () => ({
  useShallow: (selector: unknown) => selector,
}));

jest.mock('@/c-assets/newchat/light/icon_ask.svg', () => ({
  __esModule: true,
  default: { src: '/ask.svg' },
}));

jest.mock('@/c-assets/logos/ai-shifu-logo-horizontal.png', () => ({
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

jest.mock('@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook', () => ({
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
  '@/app/c/[[...id]]/Components/ChatUi/ChatComponents/useChatComponentsScroll',
  () => ({
    useChatComponentsScroll: () => ({
      scrollToLesson: jest.fn(),
    }),
  }),
);

jest.mock('./lessonFeedbackPromptState', () => ({
  findLastVisibleLessonFeedbackElementBid: () => '',
}));

jest.mock('./lessonPdfState', () => ({
  isLessonPdfContentReady: () => mockLessonPdfReady,
  shouldExcludeLessonPdfInteraction: () => false,
}));

jest.mock('./useLessonPdfPrint', () => ({
  useLessonPdfPrint: () => ({
    isPreparing: mockLessonPdfPreparing,
    printLessonPdf: mockPrintLessonPdf,
  }),
}));

jest.mock('@/c-common/hooks/useTracking', () => ({
  useTracking: () => ({
    trackEvent: jest.fn(),
    trackTrailProgress: jest.fn(),
  }),
}));

jest.mock('@/c-service/Shifu', () => ({
  shifu: {
    resetTools: {
      resetChapter: jest.fn(),
    },
  },
}));

jest.mock('@/c-store/envStore', () => ({
  useEnvStore: Object.assign(
    (selector: (state: any) => unknown) =>
      selector({
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

jest.mock('@/c-store/useCourseStore', () => ({
  useCourseStore: (selector: (state: any) => unknown) =>
    selector({
      courseAvatar: mockCourseAvatar,
      courseName: '测试课程',
      courseTtsEnabled: true,
      openPayModal: jest.fn(),
      payModalResult: null,
      resetChapter: jest.fn(),
      resetedLessonId: null,
      resettingLessonId: null,
      updateLessonId: jest.fn(),
    }),
}));

jest.mock('@/c-store/useSystemStore', () => ({
  useSystemStore: (selector: (state: any) => unknown) =>
    selector({
      learningMode: mockLearningMode,
      updateLearningMode: jest.fn(),
    }),
}));

jest.mock('@/hooks/useToast', () => ({
  fail: jest.fn(),
  toast: jest.fn(),
}));

jest.mock('@/hooks/useExclusiveAudio', () => ({
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
    function MockAskBlock() {
      return <div />;
    },
);
jest.mock(
  './ContentBlock',
  () =>
    function MockContentBlock({
      item,
      contentRenderKey,
      enableStreamingTypewriter,
    }: {
      item: { content?: string; element_bid?: string };
      contentRenderKey?: string;
      enableStreamingTypewriter?: boolean;
    }) {
      return (
        <div
          data-testid={`content-block-${item.element_bid || 'item'}`}
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
    function MockInteractionBlock() {
      return <div />;
    },
);
jest.mock(
  './InteractionBlockM',
  () =>
    function MockInteractionBlockM() {
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
    function MockListenModeSlideRenderer() {
      return <div data-testid='listen-mode-renderer' />;
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

const setMockChatLogicItems = (items: Array<Record<string, unknown>>) => {
  mockUseChatLogicHook.mockReturnValue({
    currentStreamingElementBid: '',
    currentTypewriterElementBid: '',
    isLoading: false,
    isOutputInProgress: false,
    items,
    lessonFeedbackPopup: {
      defaultCommentText: '',
      defaultScoreText: '',
      onClose: jest.fn(),
      onSubmit: jest.fn(),
      open: false,
      readonly: false,
    },
    onRefresh: jest.fn(),
    onSend: jest.fn(),
    reGenerateConfirm: {
      onCancel: jest.fn(),
      onConfirm: jest.fn(),
      open: false,
    },
    requestAudioForBlock: jest.fn(),
    showLessonUpdateNotice: true,
    toggleAskExpanded: jest.fn(),
  });
};

const createNewChatComponentsElement = (
  onLessonUpdateNoticeVisibilityChange: jest.Mock,
  onLessonPdfActionChange: jest.Mock,
) => (
  <AppContext.Provider
    value={{
      frameLayout: 1,
      isLoggedIn: true,
      mobileStyle: false,
      theme: 'light',
      userInfo: null,
    }}
  >
    <NewChatComponents
      chapterId='chapter-1'
      chapterUpdate={jest.fn()}
      getNextLessonId={jest.fn()}
      lessonHasContentUpdate={true}
      lessonId='lesson-1'
      lessonTitle='第一课'
      lessonUpdate={jest.fn()}
      onGoChapter={jest.fn()}
      onPurchased={jest.fn()}
      updateSelectedLesson={jest.fn()}
      onLessonUpdateNoticeVisibilityChange={
        onLessonUpdateNoticeVisibilityChange
      }
      onLessonPdfActionChange={onLessonPdfActionChange}
    />
  </AppContext.Provider>
);

const renderNewChatComponents = (
  onLessonUpdateNoticeVisibilityChange = jest.fn(),
  onLessonPdfActionChange = jest.fn(),
  items: Array<Record<string, unknown>> = [],
) => {
  setMockChatLogicItems(items);
  const renderElement = () =>
    createNewChatComponentsElement(
      onLessonUpdateNoticeVisibilityChange,
      onLessonPdfActionChange,
    );
  const renderResult = render(renderElement());

  return Object.assign(renderResult, {
    rerenderWithItems(nextItems: Array<Record<string, unknown>>) {
      setMockChatLogicItems(nextItems);
      renderResult.rerender(renderElement());
    },
  });
};

const renderTitlebarLessonUpdateNotice = () =>
  render(
    <LessonUpdateNotice
      chapterId='chapter-1'
      lessonId='lesson-1'
      lessonTitle='第一课'
    />,
  );

describe('NewChatComponents', () => {
  let requestAnimationFrameSpy: jest.SpyInstance;
  let visibilityStateSpy: jest.SpyInstance;
  let documentVisibilityState: DocumentVisibilityState;

  beforeEach(() => {
    jest.clearAllMocks();
    Object.assign(window.location, {
      href: 'http://localhost:3000/c/course-1?lessonid=lesson-1&mode=listen&preview=true#follow-up',
      pathname: '/c/course-1',
      search: '?lessonid=lesson-1&mode=listen&preview=true',
      hash: '#follow-up',
    });
    mockCourseAvatar = '';
    mockLearningMode = 'listen';
    mockLogoHorizontal = '';
    mockLogoWideUrl = '';
    mockOfficialSiteUrl = 'https://official.example.com';
    mockLessonPdfReady = false;
    mockLessonPdfPreparing = false;
    documentVisibilityState = 'visible';
    visibilityStateSpy = jest
      .spyOn(document, 'visibilityState', 'get')
      .mockImplementation(() => documentVisibilityState);
    requestAnimationFrameSpy = jest
      .spyOn(window, 'requestAnimationFrame')
      .mockImplementation(() => 0);
  });

  afterEach(() => {
    requestAnimationFrameSpy.mockRestore();
    visibilityStateSpy.mockRestore();
  });

  it('renders the titlebar retake action and opens the existing confirm dialog', async () => {
    renderTitlebarLessonUpdateNotice();

    const retakeAction = screen.getByRole('button', {
      name: '重修本节课程',
    });
    expect(retakeAction.closest('span')).toHaveTextContent(
      '本节课程已更新，建议重修',
    );
    expect(retakeAction).toHaveTextContent('重修');

    const user = userEvent.setup();
    await act(async () => {
      await user.click(retakeAction);
    });

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('确认重修')).toBeInTheDocument();
    expect(
      screen.getByText('重修会清空本节学习数据。确定重修？'),
    ).toBeInTheDocument();
  });

  it('reports the notice visibility without rendering it in chat content', async () => {
    const onLessonUpdateNoticeVisibilityChange = jest.fn();
    renderNewChatComponents(onLessonUpdateNoticeVisibilityChange);

    await waitFor(() => {
      expect(onLessonUpdateNoticeVisibilityChange).toHaveBeenLastCalledWith(
        true,
      );
    });
    expect(
      screen.queryByRole('button', {
        name: '重修本节课程',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('本节课程已更新，建议重修'),
    ).not.toBeInTheDocument();
  });

  it('finishes visible read content immediately when the page becomes hidden', async () => {
    mockLearningMode = 'read';
    const initialItems: Array<Record<string, unknown>> = [
      {
        content: '正在打字的正文',
        element_bid: 'text-1',
        element_type: 'text',
        is_final: false,
        shouldUseTypewriter: true,
        type: 'content',
      },
      {
        content: '<div>已经收到的后续内容</div>',
        element_bid: 'html-1',
        element_type: 'html',
        type: 'content',
      },
    ];
    const backgroundItems: Array<Record<string, unknown>> = [
      {
        ...initialItems[0],
        content: '正在打字的正文，以及后台收到的增量',
      },
      {
        content: '后台收到的新正文块',
        element_bid: 'text-2',
        element_type: 'text',
        is_final: false,
        shouldUseTypewriter: true,
        type: 'content',
      },
      initialItems[1],
    ];
    const { rerenderWithItems } = renderNewChatComponents(
      jest.fn(),
      jest.fn(),
      initialItems,
    );

    expect(screen.getByTestId('content-block-text-1')).toHaveAttribute(
      'data-typewriter',
      'true',
    );
    expect(
      screen.queryByTestId('content-block-html-1'),
    ).not.toBeInTheDocument();

    act(() => {
      documentVisibilityState = 'hidden';
      document.dispatchEvent(new Event('visibilitychange'));
    });

    await waitFor(() => {
      expect(screen.getByTestId('content-block-text-1')).toHaveAttribute(
        'data-typewriter',
        'false',
      );
      expect(screen.getByTestId('content-block-text-1')).toHaveAttribute(
        'data-content-render-key',
        'text-1:hidden',
      );
      expect(screen.getByTestId('content-block-html-1')).toBeInTheDocument();
    });

    // Make a background SSE update available to the hook without committing a
    // component render first. The foreground event must suppress this latest
    // snapshot before typewriter mode can resume.
    setMockChatLogicItems(backgroundItems);
    act(() => {
      documentVisibilityState = 'visible';
      document.dispatchEvent(new Event('visibilitychange'));
    });

    await waitFor(() => {
      expect(screen.getByTestId('content-block-text-1')).toHaveTextContent(
        '正在打字的正文，以及后台收到的增量',
      );
      expect(screen.getByTestId('content-block-text-1')).toHaveAttribute(
        'data-typewriter',
        'false',
      );
      expect(screen.getByTestId('content-block-text-1')).toHaveAttribute(
        'data-content-render-key',
        'text-1:suppressed',
      );
      expect(screen.getByTestId('content-block-text-2')).toHaveAttribute(
        'data-typewriter',
        'false',
      );
      expect(screen.getByTestId('content-block-text-2')).toHaveAttribute(
        'data-content-render-key',
        'text-2:suppressed',
      );
      expect(screen.getByTestId('content-block-html-1')).toBeInTheDocument();
    });

    act(() => {
      rerenderWithItems([
        ...backgroundItems,
        {
          content: '回到前台后收到的新正文块',
          element_bid: 'text-3',
          element_type: 'text',
          is_final: false,
          shouldUseTypewriter: true,
          type: 'content',
        },
      ]);
    });

    await waitFor(() => {
      expect(screen.getByTestId('content-block-text-3')).toHaveAttribute(
        'data-typewriter',
        'true',
      );
      expect(screen.getByTestId('content-block-text-3')).not.toHaveAttribute(
        'data-content-render-key',
      );
    });
  });

  it('exposes the PDF action while a desktop slide mode is active', async () => {
    mockLessonPdfReady = true;
    const onLessonPdfActionChange = jest.fn();

    renderNewChatComponents(jest.fn(), onLessonPdfActionChange);

    await waitFor(() => {
      expect(onLessonPdfActionChange).toHaveBeenLastCalledWith({
        lessonId: 'lesson-1',
        isFollowUpStreaming: false,
        isPreparing: false,
        onDownload: mockPrintLessonPdf,
      });
    });
    expect(screen.getByTestId('listen-mode-renderer')).toBeInTheDocument();
  });

  it('keeps the slide renderer mounted while preparing the read-mode print tree', async () => {
    mockLessonPdfReady = true;
    mockLessonPdfPreparing = true;

    const { container } = renderNewChatComponents();

    expect(screen.getByTestId('listen-mode-renderer')).toBeInTheDocument();
    expect(
      container.querySelector('[data-lesson-print-scroll="true"]'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('lesson-pdf-preparing-overlay'),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        container.querySelector('[data-lesson-print-course-qr="true"]'),
      ).toBeInTheDocument();
    });
  });

  it('ends the print tree with a QR code for the course page only', async () => {
    mockLearningMode = 'read';

    const { container } = renderNewChatComponents();
    const footer = await waitFor(() => {
      const element = container.querySelector(
        '[data-lesson-print-course-qr="true"]',
      );
      expect(element).toBeInTheDocument();
      return element as HTMLElement;
    });
    const courseUrl = `${window.location.origin}/c/course-1`;
    const link = footer.querySelector('a');
    const qrCode = footer.querySelector('svg');

    expect(footer).toHaveAttribute('data-lesson-print-only', 'true');
    expect(footer).toHaveTextContent('扫码进入课程，获得一对一讲解与答疑');
    expect(link).toHaveAttribute('href', courseUrl);
    expect(link).toHaveAttribute(
      'aria-label',
      '扫码进入课程，获得一对一讲解与答疑',
    );
    expect(qrCode).toHaveAttribute('width', '144');
    expect(qrCode).toHaveAttribute('height', '144');
    expect(qrCode?.querySelector('title')).toHaveTextContent(
      '扫码进入课程，获得一对一讲解与答疑',
    );
    expect(footer.nextElementSibling).toHaveAttribute('id', 'chat-box-bottom');
  });

  it('groups printable lesson sections under the print page width scope', async () => {
    mockLearningMode = 'read';

    const { container } = renderNewChatComponents(jest.fn(), jest.fn(), [
      {
        content: '课时正文',
        element_bid: 'content-1',
        type: 'content',
      },
      {
        ask_list: [],
        element_bid: 'ask-1',
        isAskExpanded: true,
        parent_element_bid: 'content-1',
        type: 'ask',
      },
      {
        content: '?[选择答案](answer)',
        element_bid: 'interaction-1',
        type: 'interaction',
      },
    ]);
    const printPage = container.querySelector<HTMLElement>(
      '[data-lesson-print-scroll="true"] > [data-lesson-print-content-page="true"]',
    );
    const printHeader = container
      .querySelector('[data-lesson-print-course-name="true"]')
      ?.closest('header');
    const lessonContent = screen.getByTestId('content-block-content-1');
    const followUp = container.querySelector<HTMLElement>(
      '[data-lesson-print-follow-up="true"]',
    );
    const interaction = container.querySelector<HTMLElement>(
      '[data-lesson-print-interaction="true"]',
    );
    const footer = await waitFor(() => {
      const element = container.querySelector<HTMLElement>(
        '[data-lesson-print-course-qr="true"]',
      );
      expect(element).toBeInTheDocument();
      return element as HTMLElement;
    });

    expect(printPage).toContainElement(printHeader as HTMLElement);
    expect(printHeader?.parentElement).toBe(printPage);
    expect(printPage).toContainElement(lessonContent);
    expect(lessonContent.parentElement?.parentElement).toBe(printPage);
    expect(followUp?.parentElement).toBe(printPage);
    expect(interaction?.parentElement).toBe(printPage);
    expect(printPage).toContainElement(footer);
    expect(footer.parentElement).toBe(printPage);
  });

  it('includes the course avatar, site brand, and official link in the print header', () => {
    mockCourseAvatar = '/course-avatar.png';
    mockLearningMode = 'read';
    mockLogoHorizontal = '/runtime-horizontal-logo.png';
    mockLogoWideUrl = '/configured-wide-logo.png';
    mockOfficialSiteUrl = 'https://learn.example.com';

    const { container } = renderNewChatComponents();

    const courseAvatar = container.querySelector(
      '[data-lesson-print-course-avatar="true"]',
    );
    const siteBrand = container.querySelector<HTMLElement>(
      '[data-lesson-print-site-brand="true"]',
    );
    const siteLogo = container.querySelector<HTMLImageElement>(
      '[data-lesson-print-site-logo="true"]',
    );
    const siteUrl = container.querySelector<HTMLAnchorElement>(
      '[data-lesson-print-site-url="true"]',
    );
    expect(courseAvatar).toHaveAttribute('src', '/course-avatar.png');
    expect(courseAvatar).toHaveAttribute('loading', 'eager');
    expect(siteBrand).toHaveClass('ml-auto', 'items-end', 'text-right');
    expect(siteBrand).toContainElement(siteLogo);
    expect(siteBrand).toContainElement(siteUrl);
    expect(siteLogo).toHaveAttribute('src', '/configured-wide-logo.png');
    expect(siteLogo).toHaveAttribute('loading', 'eager');
    expect(siteUrl).toBeInstanceOf(HTMLAnchorElement);
    expect(siteUrl).toHaveAttribute('href', 'https://learn.example.com');
    expect(siteUrl).toHaveAttribute('target', '_blank');
    expect(siteUrl).toHaveAttribute('rel', 'noopener noreferrer');
    expect(siteUrl).toHaveTextContent('https://learn.example.com');
    expect(siteLogo?.nextElementSibling).toBe(siteUrl);
    expect(
      container.querySelector('[data-lesson-print-course-name="true"]'),
    ).toHaveTextContent('测试课程');
    expect(
      container.querySelector('[data-lesson-print-lesson-title="true"]'),
    ).toHaveTextContent('第一课');
  });

  it('keeps the configured site brand when the course has no avatar', () => {
    mockLearningMode = 'read';
    mockLogoHorizontal = '/runtime-horizontal-logo.png';

    const { container } = renderNewChatComponents();

    expect(
      container.querySelector('[data-lesson-print-course-avatar="true"]'),
    ).not.toBeInTheDocument();
    expect(
      container.querySelector('[data-lesson-print-site-logo="true"]'),
    ).toHaveAttribute('src', '/runtime-horizontal-logo.png');
  });

  it('uses the default brand only when the site has no logo configuration', () => {
    mockLearningMode = 'read';

    const { container } = renderNewChatComponents();

    expect(
      container.querySelector('[data-lesson-print-site-logo="true"]'),
    ).toHaveAttribute('src', '/ai-shifu-logo-horizontal.png');
  });
});
