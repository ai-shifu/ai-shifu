import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppContext } from '../AppContext';
import { NewChatComponents } from './NewChatComp';
import LessonUpdateNotice from '../LessonUpdateNotice';

const mockUseChatLogicHook = jest.fn();

jest.mock('react-i18next', () => {
  const translations: Record<string, string> = {
    'common.core.cancel': '取消',
    'common.core.ok': '确认',
    'module.chat.ask': '追问',
    'module.chat.lessonUpdateRecommendRetake':
      '本节课程已更新，建议<action>重修</action>',
    'module.chat.lessonUpdateRetakeAccessibleLabel': '重修本节课程',
    'module.chat.lessonUpdateRetakeAction': '重修',
    'module.lesson.reset.confirmContent': '重修会清空本节学习数据。确定重修？',
    'module.lesson.reset.confirmTitle': '确认重修',
    'module.renderUi.core.confirm': '确认',
    'module.renderUi.core.copied': '已复制',
    'module.renderUi.core.copyCode': '复制代码',
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
  useEnvStore: {
    getState: () => ({
      courseId: 'shifu-1',
    }),
  },
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
      courseAvatar: '',
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
      learningMode: 'listen',
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
    function MockContentBlock() {
      return <div />;
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
      return <div />;
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
jest.mock('@/components/audio/AudioPlayer', () => ({
  AudioPlayer: function MockAudioPlayer() {
    return <div />;
  },
}));

const renderNewChatComponents = (
  onLessonUpdateNoticeVisibilityChange = jest.fn(),
) => {
  mockUseChatLogicHook.mockReturnValue({
    currentStreamingElementBid: '',
    currentTypewriterElementBid: '',
    isLoading: false,
    isOutputInProgress: false,
    items: [],
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

  return render(
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
      />
    </AppContext.Provider>,
  );
};

const renderTitlebarLessonUpdateNotice = () =>
  render(
    <LessonUpdateNotice
      chapterId='chapter-1'
      lessonId='lesson-1'
      lessonTitle='第一课'
    />,
  );

describe('NewChatComponents lesson update notice', () => {
  let requestAnimationFrameSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    requestAnimationFrameSpy = jest
      .spyOn(window, 'requestAnimationFrame')
      .mockImplementation(() => 0);
  });

  afterEach(() => {
    requestAnimationFrameSpy.mockRestore();
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
});
