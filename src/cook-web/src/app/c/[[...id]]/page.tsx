'use client';

import styles from './page.module.scss';

import { useEffect, useState, useCallback, useMemo } from 'react';
import clsx from 'clsx';
import { useShallow } from 'zustand/react/shallow';
import { useTranslation } from 'react-i18next';

import { useParams } from 'next/navigation';

import {
  calcFrameLayout,
  FRAME_LAYOUT_MOBILE,
  inWechat,
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
import { useLessonTree } from './hooks/useLessonTree';
import { updateWxcode } from '@/c-api/user';
import { shifu } from '@/c-service/Shifu';
import { buildLoginRedirectPath } from '@/c-utils/urlUtils';

import { Skeleton } from '@/components/ui/Skeleton';
import { AppContext } from './Components/AppContext';
import NavDrawer from './Components/NavDrawer/NavDrawer';
import FeedbackModal from './Components/FeedbackModal/FeedbackModal';
import TrackingVisit from '@/c-components/TrackingVisit';
import ChatUi from './Components/ChatUi/ChatUi';

import ChatMobileHeader from './Components/ChatMobileHeader';
import PayModalM from './Components/Pay/PayModalM';
import PayModal from './Components/Pay/PayModal';

// import LoginModal from './Components/Login/LoginModal';

// the main page of course learning
export default function ChatPage() {
  const { t, i18n } = useTranslation();

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
  function gotoLogin() {
    const redirectPath = buildLoginRedirectPath(window.location.href);
    window.location.href = `/login?redirect=${encodeURIComponent(redirectPath)}`;
  }
  // NOTE: Probably don't need this.
  // const [loginModalOpen, setLoginModalOpen] = useState(false);

  /**
   * UI layout part
   */
  const { frameLayout, updateFrameLayout } = useUiLayoutStore(state => state);
  const mobileStyle = frameLayout === FRAME_LAYOUT_MOBILE;

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

  // check the frame layout
  useEffect(() => {
    const onResize = () => {
      const frameLayout = calcFrameLayout('#root');
      updateFrameLayout(frameLayout);
    };
    window.addEventListener('resize', onResize);
    onResize();
    return () => {
      window.removeEventListener('resize', onResize);
    };
  }, [updateFrameLayout]);

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
    if (selectedLessonId) {
      updateLessonId(selectedLessonId);
    }
  }, [selectedLessonId, updateLessonId]);

  const loadData = useCallback(async () => {
    await loadTree(chapterId, lessonId);
  }, [chapterId, lessonId, loadTree]);

  const [loadedChapterId, setLoadedChapterId] = useState<string | null>(null);
  useEffect(() => {
    if (initialized && loadedChapterId !== chapterId) {
      loadData();
      setLoadedChapterId(chapterId);
    }
  }, [chapterId, initialized, loadData, loadedChapterId]);

  const resolvedLessonId = selectedLessonId || lessonId;
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
    const chapter = getChapterByLesson(id);
    if (!chapter) {
      return;
    }
    updateLessonId(id);
    if (chapter.id !== chapterId) {
      updateChapterId(chapter.id);
    }
    if (lessonId === id) {
      return;
    }
    events.dispatchEvent(
      new CustomEvent(EVENT_NAMES.GO_TO_NAVIGATION_NODE, {
        detail: {
          chapterId: chapter.id,
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

  const onGoChapter = async id => {
    // updateChapterId(id);
    updateLessonId(id);
  };

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
      await reloadTree(e.detail.chapter_id, e.detail.lesson_id);
      onGoChapter(e.detail.lesson_id);
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
  }, [gotoLogin, onGoChapter, reloadTree]);

  return (
    <div
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

        {payModalOpen && mobileStyle ? (
          <PayModalM
            open={payModalOpen}
            onCancel={_onPayModalCancel}
            onOk={_onPayModalOk}
            type={payModalState.type}
            payload={payModalState.payload}
          />
        ) : null}

        {payModalOpen && !mobileStyle ? (
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
