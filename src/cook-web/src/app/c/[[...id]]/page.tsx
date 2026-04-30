'use client';

import styles from './page.module.scss';

import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import clsx from 'clsx';
import { useShallow } from 'zustand/react/shallow';
import { useTranslation } from 'react-i18next';
import type { MobileViewMode } from 'markdown-flow-ui/slide';

import { useParams, useSearchParams } from 'next/navigation';

import {
  calcFrameLayout,
  FRAME_LAYOUT_MOBILE,
  inWechat,
  inMiniProgram,
} from '@/c-constants/uiConstants';
import { EVENT_NAMES, events } from './events';

import {
  useEnvStore,
  useCourseStore,
  useUiLayoutStore,
  useSystemStore,
} from '@/c-store';
import { useUserStore } from '@/store';
import { useDisclosure } from '@/c-common/hooks/useDisclosure';
import { useTracking } from '@/c-common/hooks/useTracking';
import { useLessonTree } from './hooks/useLessonTree';
import {
  applyLessonSelection,
  resolveRequestedLessonId,
} from './lessonNavigation';
import { updateWxcode } from '@/c-api/user';
import { shifu } from '@/c-service/Shifu';
import {
  buildLoginRedirectPath,
  getLessonIdFromQuery,
  replaceCurrentUrlWithLessonId,
} from '@/c-utils/urlUtils';

import { Skeleton } from '@/components/ui/Skeleton';
import { AppContext } from './Components/AppContext';
import NavDrawer from './Components/NavDrawer/NavDrawer';
import FeedbackModal from './Components/FeedbackModal/FeedbackModal';
import TrackingVisit from '@/c-components/TrackingVisit';
import ChatUi from './Components/ChatUi/ChatUi';
import {
  DEFAULT_LISTEN_MOBILE_VIEW_MODE,
  LISTEN_MODE_VH_FALLBACK_CLASSNAME,
} from './Components/ChatUi/listenModeTypes';

import dynamic from 'next/dynamic';
import ChatMobileHeader from './Components/ChatMobileHeader';
import MiniProgramPayGuide from './Components/Pay/MiniProgramPayGuide';
import { trackCourseVisitIfNeeded } from './courseVisitTracking';

const PayModalM = dynamic(() => import('./Components/Pay/PayModalM'), {
  ssr: false,
});
const PayModal = dynamic(() => import('./Components/Pay/PayModal'), {
  ssr: false,
});

// import LoginModal from './Components/Login/LoginModal';

// the main page of course learning
const getIsLandscapeViewport = () => {
  if (typeof window === 'undefined') {
    return false;
  }

  return (
    window.matchMedia('(orientation: landscape)').matches ||
    window.innerWidth > window.innerHeight
  );
};

const isEditableElement = (element: Element | null) => {
  if (!element) {
    return false;
  }

  if (element instanceof HTMLInputElement) {
    const inputType = element.type;
    return ![
      'button',
      'checkbox',
      'file',
      'hidden',
      'radio',
      'reset',
      'submit',
    ].includes(inputType);
  }

  return (
    element instanceof HTMLTextAreaElement ||
    (element instanceof HTMLElement && element.isContentEditable)
  );
};

const isEditableElementFocused = () => {
  if (typeof document === 'undefined') {
    return false;
  }

  return isEditableElement(document.activeElement);
};

export default function ChatPage() {
  const { t, i18n } = useTranslation();
  const { trackEvent } = useTracking();
  const attemptedCourseVisitKeyRef = useRef<string | null>(null);
  const pendingCourseVisitKeyRef = useRef<string | null>(null);
  const initialCourseVisitEntryTypeRef = useRef<'catalog' | 'deep_link' | null>(
    null,
  );

  /**
   * User info and init part
   */
  const userInfo = useUserStore(state => state.userInfo);
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  const isUserInitialized = useUserStore(state => state.isInitialized);
  const initialized = isUserInitialized;

  const { wechatCode, previewMode, learningMode } = useSystemStore(
    useShallow(state => ({
      wechatCode: state.wechatCode,
      previewMode: state.previewMode,
      learningMode: state.learningMode,
    })),
  );
  const isListenMode = learningMode === 'listen';

  useEffect(() => {
    if (!initialized) {
      return;
    }
    if (!isLoggedIn) {
      return;
    }
    if (!wechatCode || !inWechat()) {
      return;
    }

    const token = useUserStore.getState().getToken();
    if (!token) {
      return;
    }

    void updateWxcode({ wxcode: wechatCode }).catch(err => {
      // eslint-disable-next-line no-console
      console.warn('Failed to update WeChat OpenID:', err);
    });
  }, [initialized, isLoggedIn, wechatCode]);

  // NOTE: User-related features should be organized into one module
  const gotoLogin = useCallback(() => {
    const redirectPath = buildLoginRedirectPath(window.location.href);
    window.location.href = `/login?redirect=${encodeURIComponent(redirectPath)}`;
  }, []);
  // NOTE: Probably don't need this.
  // const [loginModalOpen, setLoginModalOpen] = useState(false);

  /**
   * UI layout part
   */
  const { frameLayout, updateFrameLayout } = useUiLayoutStore(state => state);
  const mobileStyle = frameLayout === FRAME_LAYOUT_MOBILE;
  const [listenMobileViewMode, setListenMobileViewMode] =
    useState<MobileViewMode>(DEFAULT_LISTEN_MOBILE_VIEW_MODE);
  const [isLandscapeViewport, setIsLandscapeViewport] = useState(false);
  const shouldUseVhViewportUnit =
    isListenMode &&
    mobileStyle &&
    isLandscapeViewport &&
    listenMobileViewMode === 'fullscreen';

  useEffect(() => {
    const root = document.getElementById('root');
    const html = document.documentElement;
    // Sync listen mode to global layout classes.
    html.classList.toggle('listen-mode', isListenMode);
    document.body.classList.toggle('listen-mode', isListenMode);
    root?.classList.toggle('listen-mode', isListenMode);
    return () => {
      html.classList.remove('listen-mode');
      document.body.classList.remove('listen-mode');
      root?.classList.remove('listen-mode');
    };
  }, [isListenMode]);

  useEffect(() => {
    if (mobileStyle) {
      setIsLandscapeViewport(getIsLandscapeViewport());
      return;
    }

    setIsLandscapeViewport(false);
  }, [mobileStyle]);

  useEffect(() => {
    if (!isListenMode || !mobileStyle) {
      setListenMobileViewMode(DEFAULT_LISTEN_MOBILE_VIEW_MODE);
    }
  }, [isListenMode, mobileStyle]);

  useEffect(() => {
    const shouldIgnoreKeyboardResize = (event?: Event) =>
      mobileStyle && event?.type === 'resize' && isEditableElementFocused();

    const handleViewportChange = (event?: Event) => {
      if (shouldIgnoreKeyboardResize(event)) {
        return;
      }

      setIsLandscapeViewport(getIsLandscapeViewport());
    };
    const mediaQueryList = window.matchMedia(
      '(orientation: landscape)',
    ) as MediaQueryList & {
      addListener?: (listener: () => void) => void;
      removeListener?: (listener: () => void) => void;
    };
    const visualViewport = window.visualViewport;

    handleViewportChange();
    window.addEventListener('resize', handleViewportChange);
    window.addEventListener('orientationchange', handleViewportChange);
    visualViewport?.addEventListener('resize', handleViewportChange);

    if (typeof mediaQueryList.addEventListener === 'function') {
      mediaQueryList.addEventListener('change', handleViewportChange);
    } else {
      mediaQueryList.addListener?.(handleViewportChange);
    }

    return () => {
      window.removeEventListener('resize', handleViewportChange);
      window.removeEventListener('orientationchange', handleViewportChange);
      visualViewport?.removeEventListener('resize', handleViewportChange);

      if (typeof mediaQueryList.removeEventListener === 'function') {
        mediaQueryList.removeEventListener('change', handleViewportChange);
      } else {
        mediaQueryList.removeListener?.(handleViewportChange);
      }
    };
  }, [mobileStyle]);

  useEffect(() => {
    const root = document.getElementById('root');
    const html = document.documentElement;
    const classTargets = [html, document.body, root].filter(
      (target): target is HTMLElement => Boolean(target),
    );

    classTargets.forEach(target => {
      target.classList.toggle(
        LISTEN_MODE_VH_FALLBACK_CLASSNAME,
        shouldUseVhViewportUnit,
      );
    });

    return () => {
      classTargets.forEach(target => {
        target.classList.remove(LISTEN_MODE_VH_FALLBACK_CLASSNAME);
      });
    };
  }, [shouldUseVhViewportUnit]);

  // check the frame layout
  useEffect(() => {
    const onResize = (event?: Event) => {
      if (
        mobileStyle &&
        event?.type === 'resize' &&
        isEditableElementFocused()
      ) {
        return;
      }

      const frameLayout = calcFrameLayout('#root');
      if (frameLayout === useUiLayoutStore.getState().frameLayout) {
        return;
      }

      updateFrameLayout(frameLayout);
    };
    window.addEventListener('resize', onResize);
    onResize();
    return () => {
      window.removeEventListener('resize', onResize);
    };
  }, [mobileStyle, updateFrameLayout]);

  const {
    open: navOpen,
    onClose: onNavClose,
    onToggle: onNavToggle,
  } = useDisclosure({
    initOpen: mobileStyle ? false : true,
  });

  const { open: feedbackModalOpen, onClose: onFeedbackModalClose } =
    useDisclosure();

  /**
   * Lesson part
   */
  let courseId = '';
  const params = useParams();
  const searchParams = useSearchParams();
  const urlLessonId = getLessonIdFromQuery(searchParams);
  if (params?.id?.[0]) {
    courseId = params.id[0];
  }

  const { updateCourseId } = useEnvStore.getState();

  useEffect(() => {
    const updateCourse = async () => {
      if (courseId) {
        await updateCourseId(courseId);
      }
    };
    updateCourse();
  }, [courseId]);

  const {
    tree,
    selectedLessonId,
    loadTree,
    reloadTree,
    updateSelectedLesson,
    toggleCollapse,
    getCurrElement,
    updateLesson,
    updateChapterStatus,
    getChapterByLesson,
    onTryLessonSelect,
    getNextLessonId,
  } = useLessonTree();

  const [currentLanguage, setCurrentLanguage] = useState(i18n.language);

  useEffect(() => {
    if (tree && i18n.language !== currentLanguage) {
      setCurrentLanguage(i18n.language);
      reloadTree();
    }
  }, [i18n.language, tree, currentLanguage, reloadTree]);

  const {
    lessonId,
    updateLessonId,
    chapterId,
    updateChapterId,
    courseName,
    courseAvatar,
  } = useCourseStore(
    useShallow(state => ({
      courseName: state.courseName,
      courseAvatar: state.courseAvatar,
      lessonId: state.lessonId,
      updateLessonId: state.updateLessonId,
      chapterId: state.chapterId,
      updateChapterId: state.updateChapterId,
    })),
  );

  useEffect(() => {
    if (!courseName) {
      return;
    }
    if (previewMode) {
      document.title = `${t('module.preview.previewAll')} - ${courseName}`;
      return;
    }
    document.title = courseName;
  }, [courseName, previewMode, t]);

  useEffect(() => {
    if (typeof window === 'undefined' || !courseName) {
      return;
    }

    if (!initialCourseVisitEntryTypeRef.current) {
      initialCourseVisitEntryTypeRef.current = urlLessonId
        ? 'deep_link'
        : 'catalog';
    }

    const entryType = initialCourseVisitEntryTypeRef.current;
    const authState = isLoggedIn ? 'logged_in' : 'guest';
    const visitAttemptKey = `${courseId}:${entryType}:${previewMode ? 'preview' : 'live'}:${authState}`;

    if (
      attemptedCourseVisitKeyRef.current === visitAttemptKey ||
      pendingCourseVisitKeyRef.current === visitAttemptKey
    ) {
      return;
    }

    pendingCourseVisitKeyRef.current = visitAttemptKey;

    void trackCourseVisitIfNeeded({
      initialized,
      isLoggedIn,
      previewMode,
      shifuBid: courseId,
      entryType,
      trackEvent,
    })
      .then(tracked => {
        if (tracked) {
          attemptedCourseVisitKeyRef.current = visitAttemptKey;
        }
      })
      .finally(() => {
        if (pendingCourseVisitKeyRef.current === visitAttemptKey) {
          pendingCourseVisitKeyRef.current = null;
        }
      });
  }, [
    courseId,
    courseName,
    initialized,
    isLoggedIn,
    previewMode,
    trackEvent,
    urlLessonId,
  ]);

  useEffect(() => {
    if (selectedLessonId) {
      updateLessonId(selectedLessonId);
    }
  }, [selectedLessonId, updateLessonId]);

  const requestedLessonId = resolveRequestedLessonId(
    selectedLessonId,
    lessonId,
    urlLessonId,
  );

  const loadData = useCallback(async () => {
    await loadTree(chapterId, requestedLessonId);
  }, [chapterId, loadTree, requestedLessonId]);

  const [loadedChapterId, setLoadedChapterId] = useState<string | null>(null);

  useEffect(() => {
    if (!urlLessonId) {
      return;
    }
    setLoadedChapterId(null);
  }, [urlLessonId]);

  useEffect(() => {
    if (initialized && loadedChapterId !== chapterId) {
      loadData();
      setLoadedChapterId(chapterId);
    }
  }, [chapterId, initialized, loadData, loadedChapterId]);

  const resolvedLessonId = selectedLessonId || lessonId;
  const syncLessonUrl = useCallback((nextLessonId: string) => {
    if (!nextLessonId?.trim()) {
      return;
    }
    replaceCurrentUrlWithLessonId(nextLessonId);
  }, []);

  const currentLessonTitle = useMemo(() => {
    if (!tree || !resolvedLessonId) {
      return '';
    }
    for (const catalog of tree.catalogs || []) {
      const lesson = (catalog.lessons || []).find(
        entry => entry.id === resolvedLessonId,
      );
      if (lesson) {
        return lesson.name || '';
      }
    }
    return '';
  }, [resolvedLessonId, tree]);

  const currentLessonStatus = useMemo(() => {
    if (!tree || !resolvedLessonId) {
      return '';
    }
    for (const catalog of tree.catalogs || []) {
      const lesson = (catalog.lessons || []).find(
        entry => entry.id === resolvedLessonId,
      );
      if (lesson) {
        return lesson.status_value || lesson.status || '';
      }
    }
    return '';
  }, [resolvedLessonId, tree]);

  const onLessonSelect = ({ id }) => {
    const selection = applyLessonSelection({
      lessonId: id,
      currentChapterId: chapterId,
      getChapterByLesson,
      updateSelectedLesson,
      updateLessonId,
      updateChapterId,
      syncLessonUrl,
    });

    if (!selection) {
      return;
    }

    if (lessonId === id) {
      return;
    }
    events.dispatchEvent(
      new CustomEvent(EVENT_NAMES.GO_TO_NAVIGATION_NODE, {
        detail: {
          chapterId: selection.chapterId,
          lessonId: id,
        },
      }),
    );

    if (mobileStyle) {
      onNavClose();
    }
  };

  const onLessonUpdate = useCallback(
    val => {
      updateLesson(val.id, val);
    },
    [updateLesson],
  );

  const onGoChapter = useCallback(
    id => {
      applyLessonSelection({
        lessonId: id,
        currentChapterId: chapterId,
        forceExpand: true,
        getChapterByLesson,
        updateSelectedLesson,
        updateLessonId,
        updateChapterId,
        syncLessonUrl,
      });
    },
    [
      chapterId,
      getChapterByLesson,
      syncLessonUrl,
      updateChapterId,
      updateLessonId,
      updateSelectedLesson,
    ],
  );

  const onChapterUpdate = useCallback(
    ({ id, status, status_value }) => {
      updateChapterStatus(id, { status, status_value });
    },
    [updateChapterStatus],
  );

  const fetchData = useCallback(async () => {
    if (tree) {
      const data = await getCurrElement();
      if (data && data.lesson) {
        updateLessonId(data.lesson.id);
        if (data.catalog) {
          updateChapterId(data.catalog.id);
        }
      }
    }
  }, [tree, getCurrElement, updateLessonId, updateChapterId]);

  useEffect(() => {
    if (!selectedLessonId || selectedLessonId === urlLessonId) {
      return;
    }

    syncLessonUrl(selectedLessonId);
  }, [selectedLessonId, syncLessonUrl, urlLessonId]);

  useEffect(() => {
    if (initialized) {
      fetchData();
    }
  }, [fetchData, initialized]);

  /**
   * Pay part
   */

  const {
    payModalOpen,
    payModalState,
    openPayModal,
    closePayModal,
    setPayModalResult,
  } = useCourseStore(
    useShallow(state => ({
      payModalOpen: state.payModalOpen,
      payModalState: state.payModalState,
      openPayModal: state.openPayModal,
      closePayModal: state.closePayModal,
      setPayModalResult: state.setPayModalResult,
    })),
  );

  const onPurchased = useCallback(() => {
    reloadTree();
  }, [reloadTree]);

  const _onPayModalCancel = useCallback(
    (_?: unknown) => {
      closePayModal();
      setPayModalResult('cancel');
    },
    [closePayModal, setPayModalResult],
  );

  const _onPayModalOk = useCallback(
    (_?: unknown) => {
      closePayModal();
      setPayModalResult('ok');
      onPurchased();
    },
    [closePayModal, onPurchased, setPayModalResult],
  );

  /**
   * Misc part
   */

  const [userSettingBasicInfo, setUserSettingBasicInfo] = useState(false);
  const [showUserSettings, setShowUserSettings] = useState(false);
  // const [loginOkHandlerData, setLoginOkHandlerData] = useState(null);

  const onGoToSettingBasic = useCallback(() => {
    setUserSettingBasicInfo(true);
    setShowUserSettings(true);
    if (mobileStyle) {
      onNavClose();
    }
  }, [mobileStyle, onNavClose]);

  const onGoToSettingPersonal = useCallback(() => {
    setUserSettingBasicInfo(false);
    setShowUserSettings(true);
    if (mobileStyle) {
      onNavClose();
    }
  }, [mobileStyle, onNavClose]);

  // const onLoginModalClose = useCallback(async () => {
  //   setLoginModalOpen(false);
  //   setLoginOkHandlerData(null);
  //   await loadData();
  //   shifu.loginTools.emitLoginModalCancel();
  // }, [loadData]);

  // const onLoginModalOk = useCallback(async () => {
  //   reloadTree();
  //   shifu.loginTools.emitLoginModalOk();
  //   if (loginOkHandlerData) {
  //     if (loginOkHandlerData.type === 'pay') {
  //       shifu.payTools.openPay({
  //         ...loginOkHandlerData.payload,
  //       });
  //     }

  //     setLoginOkHandlerData(null);
  //   }
  // }, [loginOkHandlerData, reloadTree]);

  // const onFeedbackClick = useCallback(() => {
  //   onFeedbackModalOpen();
  // }, [onFeedbackModalOpen]);

  // listen global event
  useEffect(() => {
    const resetChapterEventHandler = async e => {
      const targetLessonId = e.detail.lesson_id;
      await reloadTree(e.detail.chapter_id, targetLessonId);
      updateSelectedLesson(targetLessonId, true);
      onGoChapter(targetLessonId);
      if (mobileStyle) {
        onNavClose();
      }
    };
    const eventHandler = () => {
      // setLoginModalOpen(true);
      gotoLogin();
    };

    shifu.events.addEventListener(
      shifu.EventTypes.OPEN_LOGIN_MODAL,
      eventHandler,
    );

    shifu.events.addEventListener(
      shifu.EventTypes.RESET_CHAPTER,
      resetChapterEventHandler,
    );

    return () => {
      shifu.events.removeEventListener(
        shifu.EventTypes.OPEN_LOGIN_MODAL,
        eventHandler,
      );

      shifu.events.removeEventListener(
        shifu.EventTypes.RESET_CHAPTER,
        resetChapterEventHandler,
      );
    };
  }, [
    gotoLogin,
    mobileStyle,
    onGoChapter,
    onNavClose,
    reloadTree,
    updateSelectedLesson,
  ]);

  return (
    <div
      data-testid='course-chat-page'
      className={clsx(
        styles.newChatPage,
        isListenMode ? styles.listenMode : '',
        mobileStyle ? 'flex-col' : 'h-screen flex-row',
        'flex',
      )}
    >
      <AppContext.Provider
        value={{ frameLayout, mobileStyle, isLoggedIn, userInfo, theme: '' }}
      >
        {mobileStyle ? (
          <ChatMobileHeader
            navOpen={navOpen}
            className={styles.chatMobileHeader}
            iconPopoverPayload={tree?.bannerInfo}
            onSettingClick={onNavToggle}
          />
        ) : null}

        {!initialized ? (
          <div className='flex flex-col space-y-6 p-6 container mx-auto'>
            <Skeleton className='h-[125px] rounded-xl' />
            <div className='space-y-4'>
              <Skeleton className='h-6' />
              <Skeleton className='h-6' />
              <Skeleton className='h-6' />
              <Skeleton className='h-6 w-1/3' />
              <Skeleton className='h-6' />
              <Skeleton className='h-6' />
              <Skeleton className='h-6 w-3/4' />
            </div>
          </div>
        ) : null}

        {initialized && navOpen ? (
          <NavDrawer
            courseName={courseName}
            courseAvatar={courseAvatar}
            onLoginClick={() => {
              // setLoginModalOpen(true)
              gotoLogin();
            }}
            lessonTree={tree}
            selectedLessonId={selectedLessonId || ''}
            onChapterCollapse={id => toggleCollapse({ id })}
            onLessonSelect={onLessonSelect}
            onTryLessonSelect={onTryLessonSelect}
            onBasicInfoClick={onGoToSettingBasic}
            onPersonalInfoClick={onGoToSettingPersonal}
          />
        ) : null}

        {initialized ? (
          <ChatUi
            lessonId={lessonId}
            chapterId={chapterId}
            lessonTitle={currentLessonTitle}
            lessonStatus={currentLessonStatus}
            lessonUpdate={onLessonUpdate}
            onGoChapter={onGoChapter}
            onPurchased={onPurchased}
            showUserSettings={showUserSettings}
            onUserSettingsClose={() => setShowUserSettings(false)}
            chapterUpdate={onChapterUpdate}
            userSettingBasicInfo={userSettingBasicInfo}
            updateSelectedLesson={updateSelectedLesson}
            getNextLessonId={getNextLessonId}
            isNavOpen={navOpen}
            onListenMobileViewModeChange={setListenMobileViewMode}
            showGenerateBtn={false}
          />
        ) : null}

        {/* It looks like it's no longer needed. */}
        {/* {loginModalOpen ? (
          <LoginModal
            onLogin={onLoginModalOk}
            open={loginModalOpen}
            onClose={onLoginModalClose}
            destroyOnClose={true}
            onFeedbackClick={onFeedbackClick}
          />
        ) : null} */}

        {payModalOpen && inMiniProgram() ? (
          <MiniProgramPayGuide
            open={payModalOpen}
            onClose={_onPayModalCancel}
          />
        ) : null}

        {payModalOpen && !inMiniProgram() && mobileStyle ? (
          <PayModalM
            open={payModalOpen}
            onCancel={_onPayModalCancel}
            onOk={_onPayModalOk}
            type={payModalState.type}
            payload={payModalState.payload}
          />
        ) : null}

        {payModalOpen && !inMiniProgram() && !mobileStyle ? (
          <PayModal
            open={payModalOpen}
            onCancel={_onPayModalCancel}
            onOk={_onPayModalOk}
            type={payModalState.type}
            payload={payModalState.payload}
          />
        ) : null}

        {initialized ? <TrackingVisit /> : null}

        <FeedbackModal
          open={feedbackModalOpen}
          onClose={onFeedbackModalClose}
        />
      </AppContext.Provider>
    </div>
  );
}
