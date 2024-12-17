import { useEffect, useState, useCallback } from 'react';
import { useEffectOnce } from 'react-use';
import { useParams, useNavigate } from 'react-router-dom';
import classNames from 'classnames';
import styles from './NewChatPage.module.scss';
import { Skeleton } from 'antd';
import {
  calcFrameLayout,
  FRAME_LAYOUT_MOBILE,
  inWechat,
} from 'constants/uiConstants.js';
import { useUiLayoutStore } from 'stores/useUiLayoutStore.js';
import { useUserStore } from 'stores/useUserStore.js';
import { AppContext } from 'Components/AppContext.js';
import NavDrawer from './Components/NavDrawer/NavDrawer.jsx';
import ChatUi from './Components/ChatUi/ChatUi.jsx';
import LoginModal from './Components/Login/LoginModal.jsx';
import { useLessonTree } from './hooks/useLessonTree.js';
import { useCourseStore } from 'stores/useCourseStore';
import TrackingVisit from 'Components/TrackingVisit.jsx';
import ChatMobileHeader from './Components/ChatMobileHeader.jsx';
import { useDisclosture } from 'common/hooks/useDisclosture.js';
import { updateWxcode } from 'Api/user.js';

import FeedbackModal from './Components/FeedbackModal/FeedbackModal.jsx';
import { useTranslation } from 'react-i18next';
import { useEnvStore } from 'stores/envStore.js';
// 课程学习主页面
const NewChatPage = (props) => {
  const { frameLayout, updateFrameLayout } = useUiLayoutStore((state) => state);
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const { hasLogin, userInfo, checkLogin ,refreshUserInfo} = useUserStore((state) => state);
  const [language, setLanguage] = useState(userInfo?.language || 'en-US');
  const {
    tree,
    loadTree,
    reloadTree,
    updateSelectedLesson,
    toggleCollapse,
    checkChapterAvaiableStatic,
    getCurrElementStatic,
    updateLesson,
    updateChapterStatus,
    getChapterByLesson,
    onTryLessonSelect,
  } = useLessonTree();
  const [cid,setCid]=useState(null)
  const { lessonId, changeCurrLesson, chapterId, updateChapterId } =
    useCourseStore((state) => state);
  const [showUserSettings, setShowUserSettings] = useState(false);
  const { open: feedbackModalOpen, onOpen: onFeedbackModalOpen, onClose: onFeedbackModalClose } = useDisclosture();
  const { i18n } = useTranslation();

  const mobileStyle = frameLayout === FRAME_LAYOUT_MOBILE;


  const {
    open: navOpen,
    onClose: onNavClose,
    onToggle: onNavToggle,
  } = useDisclosture({
    initOpen: mobileStyle ? false : true,
  });

  // 判断布局类型
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

  const loadData = useCallback(async () => {
    await loadTree();
  }, [loadTree]);

  const initAndCheckLogin = useCallback(async () => {
    await checkLogin();
    if (inWechat()) {
      await updateWxcode();
    }
    setInitialized(true);
  }, [checkLogin]);
  const {courseId} = useParams();
  const { updateCourseId } = useEnvStore.getState();
  useEffect(() => {
    const updateCourse = async () => {
      if (courseId) {
        await updateCourseId(courseId);
      }
    };
    updateCourse();
  }, [courseId, updateCourseId]);
  const checkUrl = useCallback(async () => {
    let nextTree = tree;
    if (!tree) {
      nextTree = await loadTree(cid, lessonId);
    } else {
      nextTree = await reloadTree(cid, lessonId);
    }

    if (cid) {
      if (!checkChapterAvaiableStatic(nextTree, cid)) {
        setCid(null);
      } else {
        const data = await getCurrElementStatic(nextTree);
        if (data) {
          changeCurrLesson(data.lesson.id);
        }
      }
    } else {
      const data = await getCurrElementStatic(nextTree);
      if (!data) {
        return;
      }
      if (data) {
        changeCurrLesson(data.lesson.id);
      }
      if (data.catalog) {
        setCid(data.catalog.id);
      }
    }
  }, [
    changeCurrLesson,
    checkChapterAvaiableStatic,
    getCurrElementStatic,
    lessonId,
    loadTree,
    reloadTree,
    tree,
  ]);

  useEffect(() => {
    if (cid === chapterId) {
      return;
    }else if (cid ){
      updateChapterId(cid);
    }
  }, [cid, chapterId, checkUrl]);

  useEffectOnce(() => {
    (async () => {
      await initAndCheckLogin();
      await checkUrl();
    })();
  });

  useEffect(() => {
    return useCourseStore.subscribe(
      (state) => state.chapterId,
      (curr, pre) => {
        checkUrl();
      }
    );
  }, [chapterId, checkUrl]);

  useEffect(() => {
    return useUserStore.subscribe(
      (state) => state.hasLogin,
      () => {
        checkUrl();
      }
    );
  }, [checkUrl]);

  useEffect(() => {
    updateSelectedLesson(lessonId);
  }, [lessonId]);

  const onLoginModalClose = useCallback(async () => {
    setLoginModalOpen(false);
    await loadData();
  }, [loadData]);

  const onLessonUpdate = useCallback(
    (val) => {
      updateLesson(val.id, val);
    },
    [updateLesson]
  );

  const onChapterUpdate = useCallback(
    ({ id, status ,status_value}) => {
      updateChapterStatus(id, { status,status_value });
    },
    [updateChapterStatus]
  );

  const onGoChapter = async (id) => {
    await reloadTree();
    setCid(id);
  };

  const onPurchased = useCallback(() => {
    reloadTree();
  }, [reloadTree]);

  const onGoToSetting = useCallback(() => {
    setShowUserSettings(true);
  }, []);

  const onLessonSelect = ({ id }) => {
    const chapter = getChapterByLesson(id);
    if (!chapter) {
      return;
    }
    changeCurrLesson(id);
    setTimeout(() => {
      if (chapter.id !== chapterId) {
        setCid(chapter.id);
      }
    }, 0);

    if (mobileStyle) {
      onNavClose();
    }
  };

  useEffect(() => {
    return useCourseStore.subscribe(
      (state) => state.resetedChapterId,
      (curr) => {
        if (!curr || curr === chapterId) {
          return;
        }
        onGoChapter(curr);
      }
    );
  });

  const onFeedbackClick = useCallback(() => {
    onFeedbackModalOpen();
  }, [onFeedbackModalOpen]);

  useEffect(() => {
      loadData();

  }, [language]);


  useEffect(() => {
    setLanguage(i18n.language);
  }, [i18n.language]);

  return (
    <div className={classNames(styles.newChatPage)}>
      <AppContext.Provider
        value={{ frameLayout, mobileStyle, hasLogin, userInfo, theme: '' }}
      >
        <Skeleton
          style={{ width: '100%', height: '100%' }}
          loading={!initialized}
          paragraph={true}
          rows={10}
        >
          {navOpen && (
            <NavDrawer
              onLoginClick={() => setLoginModalOpen(true)}
              lessonTree={tree}
              onChapterCollapse={toggleCollapse}
              onLessonSelect={onLessonSelect}
              onGoToSetting={onGoToSetting}
              onTryLessonSelect={onTryLessonSelect}
              onClose={onNavClose}
            />
          )}
          {
            <ChatUi
              chapterId={chapterId}
              lessonUpdate={onLessonUpdate}
              onGoChapter={onGoChapter}
              onPurchased={onPurchased}
              showUserSettings={showUserSettings}
              onUserSettingsClose={() => setShowUserSettings(false)}
              chapterUpdate={onChapterUpdate}
            />
          }
        </Skeleton>
        {loginModalOpen && (
          <LoginModal
            open={loginModalOpen}
            onClose={onLoginModalClose}
            destroyOnClose={true}
            onFeedbackClick={onFeedbackClick}
          />
        )}
        {initialized && <TrackingVisit />}

        {mobileStyle && (
          <ChatMobileHeader
            navOpen={navOpen}
            className={styles.chatMobileHeader}
            onSettingClick={onNavToggle}
          />
        )}

        <FeedbackModal
          open={feedbackModalOpen}
          onClose={onFeedbackModalClose}
        />
      </AppContext.Provider>
    </div>
  );
};

export default NewChatPage;
