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
  wechatLogin,
} from '@/constants/uiConstants';
import { LESSON_STATUS_VALUE } from '@/constants/courseConstants';
import { EVENT_NAMES, events } from './events';

import {
  useEnvStore,
  useCourseStore,
  useUiLayoutStore,
  useSystemStore,
} from '@/store';
import { useUserStore } from '@/store';
import { useDisclosure } from '@/hooks/useDisclosure';
import { useLessonTree, type LessonTreeLesson } from './hooks/useLessonTree';
import {
  applyLessonSelection,
  resolveRequestedLessonId,
} from './lessonNavigation';
import { updateWxcode } from '@/api/user';
import { shifu } from '@/lib/shifu/Shifu';
import type { EnvStoreState } from '@/types/store';
import {
  buildLoginRedirectPath,
  getLessonIdFromQuery,
  removeParamFromUrl,
  replaceCurrentUrlWithLessonId,
} from '@/lib/urlUtils';

import { Skeleton } from '@/components/ui/Skeleton';
import { AppContext } from './Components/AppContext';
import NavDrawer from './Components/NavDrawer/NavDrawer';
import FeedbackModal from './Components/FeedbackModal/FeedbackModal';
import ChatUi from './Components/ChatUi/ChatUi';
import {
  DEFAULT_LISTEN_MOBILE_VIEW_MODE,
  LISTEN_MODE_VH_FALLBACK_CLASSNAME,
} from './Components/ChatUi/listenModeTypes';

import dynamic from 'next/dynamic';
import ChatMobileHeader from './Components/ChatMobileHeader';
import MiniProgramPayGuide from './Components/Pay/MiniProgramPayGuide';
import { isWechatCodeFlowEnabled } from './Components/Pay/wechatJsapi';
import { useCourseProfileOnboardingGate } from './hooks/useCourseProfileOnboardingGate';
import DebugConsoleOverlay from '@/components/debug/DebugConsoleOverlay';
import LearnerProfileDialog from '@/components/profile-onboarding/LearnerProfileDialog';
import { debugWarn } from '@/lib/debugConsole';

const PayModalM = dynamic(() => import('./Components/Pay/PayModalM'), {
  ssr: false,
});
const PayModal = dynamic(() => import('./Components/Pay/PayModal'), {
  ssr: false,
});

type LessonUpdate = Pick<LessonTreeLesson, 'id'> & Partial<LessonTreeLesson>;

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

const OPENID_REBIND_SESSION_KEY = 'wechat_openid_rebind_attempted';

/**
 * Send the user through the WeChat code flow once per session to recover an
 * openid the account never got bound. The redirect target drops the spent
 * `code`/`state` so the fresh one does not stack onto them.
 */
const requestWechatCodeForOpenIdRebind = () => {
  if (typeof window === 'undefined') {
    return;
  }
  const { appId } = useEnvStore.getState() as EnvStoreState;
  if (!appId) {
    return;
  }
  try {
    if (sessionStorage.getItem(OPENID_REBIND_SESSION_KEY)) {
      return;
    }
    sessionStorage.setItem(OPENID_REBIND_SESSION_KEY, '1');
  } catch {
    // Without session storage there is no way to bound the retries, so skip
    // the redirect rather than risk looping through OAuth.
    return;
  }
  wechatLogin({
    appId,
    redirectUrl: removeParamFromUrl(window.location.href, ['code', 'state']),
  });
};

const requestWechatCodeForOpenIdRebindIfUnbound = (openId: string) => {
  if (openId) {
    return;
  }
  requestWechatCodeForOpenIdRebind();
};

export default function ChatPage() {
  const { t, i18n } = useTranslation();

  /**
   * User info and init part
   */
  const userInfo = useUserStore(state => state.userInfo);
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  const isUserInitialized = useUserStore(state => state.isInitialized);
  const refreshUserInfo = useUserStore(state => state.refreshUserInfo);
  const initialized = isUserInitialized;
  const learnerProfileScope = userInfo?.user_id || 'guest';

  const { wechatCode, previewMode, learningMode } = useSystemStore(
    useShallow(state => ({
      wechatCode: state.wechatCode,
      previewMode: state.previewMode,
      learningMode: state.learningMode,
    })),
  );
  const isSlideMode = learningMode === 'listen' || learningMode === 'classroom';
  const [lessonUpdateNoticeVisible, setLessonUpdateNoticeVisible] =
    useState(false);

  const enableWxcode = useEnvStore(
    (state: EnvStoreState) => state.enableWxcode,
  );
  const wxcodeEnabled = isWechatCodeFlowEnabled(enableWxcode);
  // Trimmed to match the backend, which strips the value before deciding
  // whether it has one: a blank string must take the rebinding path here
  // rather than reach the gateway as a missing parameter.
  const wechatOpenId = (userInfo?.openid || '').trim();
  // The account profile arrives after the login state does, and a not-yet-loaded
  // profile must not be read as "this account has no openid".
  const isUserProfileLoaded = Boolean(userInfo);
  // Tracks which OAuth code this page already spent on a binding attempt, so a
  // failed exchange is not retried in a loop with the same (single-use) code.
  const attemptedWechatCodeRef = useRef('');

  // WeChat JSAPI payment needs the openid of the WeChat account currently
  // viewing the page. Every unspent code is handed to the backend, which only
  // writes when the openid actually differs, so signing in from another WeChat
  // account moves the binding over instead of paying with a stale openid. The
  // code itself can be consumed elsewhere first (guest registration) or fail to
  // exchange, and login drops it from the URL, which used to leave an account
  // without any openid for good -- so when none is left and nothing is bound,
  // fetch a fresh code once per session.
  useEffect(() => {
    if (!initialized) {
      return;
    }
    if (!isLoggedIn || !isUserProfileLoaded) {
      return;
    }
    if (!inWechat() || inMiniProgram() || !wxcodeEnabled) {
      return;
    }

    const token = useUserStore.getState().getToken();
    if (!token) {
      return;
    }

    if (!wechatCode) {
      requestWechatCodeForOpenIdRebindIfUnbound(wechatOpenId);
      return;
    }
    if (attemptedWechatCodeRef.current === wechatCode) {
      return;
    }
    attemptedWechatCodeRef.current = wechatCode;

    void updateWxcode({ wxcode: wechatCode })
      .then(openid => {
        if (!openid) {
          debugWarn('[lesson-page] WeChat OpenID binding returned no openid');
          // The code is spent either way, and the ref stops this effect from
          // trying again with it, so an unbound account would stay unbound for
          // the rest of the session. Spend the one fresh code instead.
          requestWechatCodeForOpenIdRebindIfUnbound(wechatOpenId);
          return undefined;
        }
        if (openid === wechatOpenId) {
          return undefined;
        }
        return refreshUserInfo();
      })
      .catch(err => {
        debugWarn('[lesson-page] failed to update WeChat OpenID', err);
        requestWechatCodeForOpenIdRebindIfUnbound(wechatOpenId);
      });
  }, [
    initialized,
    isLoggedIn,
    isUserProfileLoaded,
    refreshUserInfo,
    wechatCode,
    wechatOpenId,
    wxcodeEnabled,
  ]);

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
  // WeChat JSAPI payment needs an openid: the code flow that grants one is
  // disabled on custom domains, and the binding can also be missing on domains
  // where it is enabled. Without an openid, guide the user to pay in an
  // external browser instead of showing a QR code they cannot scan in place.
  const wechatPayUnavailable =
    inWechat() &&
    !inMiniProgram() &&
    (!wxcodeEnabled || (isLoggedIn && isUserProfileLoaded && !wechatOpenId));
  const showPayGuide = inMiniProgram() || wechatPayUnavailable;
  const [listenMobileViewMode, setListenMobileViewMode] =
    useState<MobileViewMode>(DEFAULT_LISTEN_MOBILE_VIEW_MODE);
  const [isLandscapeViewport, setIsLandscapeViewport] = useState(false);
  const shouldUseVhViewportUnit =
    isSlideMode &&
    mobileStyle &&
    isLandscapeViewport &&
    listenMobileViewMode === 'fullscreen';

  useEffect(() => {
    const root = document.getElementById('root');
    const html = document.documentElement;
    // Keep the existing global layout class for both slide-based modes.
    html.classList.toggle('listen-mode', isSlideMode);
    document.body.classList.toggle('listen-mode', isSlideMode);
    root?.classList.toggle('listen-mode', isSlideMode);
    return () => {
      html.classList.remove('listen-mode');
      document.body.classList.remove('listen-mode');
      root?.classList.remove('listen-mode');
    };
  }, [isSlideMode]);

  useEffect(() => {
    if (mobileStyle) {
      setIsLandscapeViewport(getIsLandscapeViewport());
      return;
    }

    setIsLandscapeViewport(false);
  }, [mobileStyle]);

  useEffect(() => {
    if (!isSlideMode || !mobileStyle) {
      setListenMobileViewMode(DEFAULT_LISTEN_MOBILE_VIEW_MODE);
    }
  }, [isSlideMode, mobileStyle]);

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
  const debugEnabled = searchParams?.get('debug') === '1';
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
  }, [courseId, updateCourseId]);

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

  const {
    runtimeReady: profileOnboardingRuntimeReady,
    openFromMenu: openLearnerProfileFromMenu,
    dialogProps: learnerProfileDialogProps,
  } = useCourseProfileOnboardingGate({
    initialized,
    isLoggedIn,
    previewMode,
    courseName,
    learnerProfileScope,
    refreshUserInfo,
  });

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

  const currentLessonHasContentUpdate = useMemo(() => {
    if (!tree || !resolvedLessonId) {
      return false;
    }
    for (const catalog of tree.catalogs || []) {
      const lesson = (catalog.lessons || []).find(
        entry => entry.id === resolvedLessonId,
      );
      if (lesson) {
        return Boolean(lesson.has_content_update_for_current_user);
      }
    }
    return false;
  }, [resolvedLessonId, tree]);

  const currentLessonFollowUpMode = useMemo(() => {
    if (!tree || !resolvedLessonId) {
      return 'text' as const;
    }
    for (const catalog of tree.catalogs || []) {
      const lesson = (catalog.lessons || []).find(
        entry => entry.id === resolvedLessonId,
      );
      if (lesson) {
        if (lesson.follow_up_mode === 'live_voice') {
          return 'live_voice' as const;
        }
        if (lesson.follow_up_mode === 'disabled') {
          return 'disabled' as const;
        }
        return 'text' as const;
      }
    }
    return 'text' as const;
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

  const lessonUpdateSequenceRef = useRef(0);
  const latestLessonUpdatesRef = useRef(
    new Map<string, { sequence: number; value: LessonUpdate }>(),
  );
  const onLessonUpdate = useCallback(
    (val: LessonUpdate) => {
      const sequence = ++lessonUpdateSequenceRef.current;
      latestLessonUpdatesRef.current.set(val.id, { sequence, value: val });
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

  const { payModalOpen, payModalState, closePayModal, setPayModalResult } =
    useCourseStore(
      useShallow(state => ({
        payModalOpen: state.payModalOpen,
        payModalState: state.payModalState,
        closePayModal: state.closePayModal,
        setPayModalResult: state.setPayModalResult,
      })),
    );

  const onPurchased = useCallback(() => {
    reloadTree();
  }, [reloadTree]);

  const _onPayModalCancel = useCallback(() => {
    closePayModal();
    setPayModalResult('cancel');
  }, [closePayModal, setPayModalResult]);

  const _onPayModalOk = useCallback(() => {
    closePayModal();
    setPayModalResult('ok');
    onPurchased();
  }, [closePayModal, onPurchased, setPayModalResult]);

  /**
   * Misc part
   */

  // const [loginOkHandlerData, setLoginOkHandlerData] = useState(null);

  const onGoToSettingPersonal = useCallback(() => {
    openLearnerProfileFromMenu();
    if (mobileStyle) {
      onNavClose();
    }
  }, [mobileStyle, onNavClose, openLearnerProfileFromMenu]);

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
      const lessonUpdateSequenceBeforeReload = lessonUpdateSequenceRef.current;
      await reloadTree(e.detail.chapter_id, targetLessonId);
      const latestLessonUpdate =
        latestLessonUpdatesRef.current.get(targetLessonId);
      onLessonUpdate(
        latestLessonUpdate &&
          latestLessonUpdate.sequence > lessonUpdateSequenceBeforeReload
          ? latestLessonUpdate.value
          : {
              id: targetLessonId,
              status: LESSON_STATUS_VALUE.LEARNING,
              status_value: LESSON_STATUS_VALUE.LEARNING,
            },
      );
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
    onLessonUpdate,
    onNavClose,
    reloadTree,
    updateSelectedLesson,
  ]);

  return (
    <div
      data-lesson-print-page='true'
      data-testid='course-chat-page'
      className={clsx(
        styles.newChatPage,
        previewMode ? styles.previewMode : '',
        lessonUpdateNoticeVisible ? styles.lessonUpdateNoticeVisible : '',
        isSlideMode ? styles.listenMode : '',
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
            lessonUpdateNoticeVisible={lessonUpdateNoticeVisible}
            courseId={courseId}
            chapterId={chapterId}
            lessonId={resolvedLessonId}
            lessonTitle={currentLessonTitle}
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
            onPersonalInfoClick={onGoToSettingPersonal}
          />
        ) : null}

        {initialized ? (
          <ChatUi
            courseId={courseId}
            lessonId={resolvedLessonId}
            chapterId={chapterId}
            lessonTitle={currentLessonTitle}
            lessonStatus={currentLessonStatus}
            lessonHasContentUpdate={currentLessonHasContentUpdate}
            followUpMode={currentLessonFollowUpMode}
            lessonUpdate={onLessonUpdate}
            onGoChapter={onGoChapter}
            onPurchased={onPurchased}
            runtimeReady={profileOnboardingRuntimeReady}
            chapterUpdate={onChapterUpdate}
            updateSelectedLesson={updateSelectedLesson}
            getNextLessonId={getNextLessonId}
            isNavOpen={navOpen}
            onListenMobileViewModeChange={setListenMobileViewMode}
            showGenerateBtn={false}
            onLessonUpdateNoticeVisibilityChange={setLessonUpdateNoticeVisible}
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

        {payModalOpen && showPayGuide ? (
          <MiniProgramPayGuide
            open={payModalOpen}
            onClose={_onPayModalCancel}
            titleKey={
              wechatPayUnavailable
                ? 'module.pay.externalBrowserNotSupported'
                : undefined
            }
            descriptionKey={
              wechatPayUnavailable
                ? 'module.pay.externalBrowserGuide'
                : undefined
            }
          />
        ) : null}

        {payModalOpen && !showPayGuide && mobileStyle ? (
          <PayModalM
            open={payModalOpen}
            onCancel={_onPayModalCancel}
            onOk={_onPayModalOk}
            type={payModalState.type}
            payload={payModalState.payload}
          />
        ) : null}

        {payModalOpen && !showPayGuide && !mobileStyle ? (
          <PayModal
            open={payModalOpen}
            onCancel={_onPayModalCancel}
            onOk={_onPayModalOk}
            type={payModalState.type}
            payload={payModalState.payload}
          />
        ) : null}

        <LearnerProfileDialog
          key={learnerProfileScope}
          {...learnerProfileDialogProps}
        />

        <FeedbackModal
          open={feedbackModalOpen}
          onClose={onFeedbackModalClose}
        />
        <DebugConsoleOverlay enabled={debugEnabled} />
      </AppContext.Provider>
    </div>
  );
}
