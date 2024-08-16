import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import classNames from 'classnames';
import styles from './NewChatPage.module.scss';
import { Skeleton } from 'antd';
import { calcFrameLayout } from 'constants/uiConstants.js';
import { useUiLayoutStore } from 'stores/useUiLayoutStore.js';
import { useUserStore } from 'stores/useUserStore.js';
import { AppContext } from 'Components/AppContext.js';
import NavDrawer from './Components/NavDrawer/NavDrawer.jsx';
import ChatUi from './Components/ChatUi/ChatUi.jsx';
import LoginModal from './Components/Login/LoginModal.jsx';
import { useLessonTree } from './hooks/useLessonTree.js';
import { useCourseStore } from 'stores/useCourseStore';
import TrackingVisit from 'Components/TrackingVisit.jsx';

// 课程学习主页面
const NewChatPage = (props) => {
  const { frameLayout, updateFrameLayout } = useUiLayoutStore((state) => state);
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const { hasLogin, userInfo, checkLogin } = useUserStore((state) => state);
  const {
    tree,
    loadTree,
    reloadTree,
    updateSelectedLesson,
    toggleCollapse,
    checkChapterAvaiableStatic,
    getCurrElementStatic,
    updateChapter,
    getChapterByLesson,
    onTryLessonSelect,
  } = useLessonTree();
  const { cid } = useParams();
  const [currChapterId, setCurrChapterId] = useState(null);
  const { lessonId, changeCurrLesson } = useCourseStore((state) => state);
  const [showUserSettings, setShowUserSettings] = useState(false);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  // 判断布局类型
  useEffect(() => {
    const onResize = () => {
      const frameLayout = calcFrameLayout('#root');
      console.log('frame layout: ', frameLayout);
      updateFrameLayout(frameLayout);
    };
    window.addEventListener('resize', onResize);
    onResize();
    return () => {
      window.removeEventListener('resize', onResize);
    };
  }, []);

  const loadData = async () => {
    await loadTree();
  };

  useEffect(() => {
    if (!initialized) {
      (async () => {
        await checkLogin();
        setInitialized(true);
      })();
    }
  }, []);

  // 定位当前课程位置
  useEffect(() => {
    if (!initialized) {
      return;
    }
    (async () => {
      let nextTree;
      if (!tree) {
        setLoading(true);
        nextTree = await loadTree(cid, lessonId);
      } else {
        setLoading(true);
        nextTree = await reloadTree(cid, lessonId);
      }

      setLoading(false);
      if (cid) {
        if (!checkChapterAvaiableStatic(nextTree, cid)) {
          navigate('/newchat');
        } else {
          const data = getCurrElementStatic(nextTree);
          if (data) {
            changeCurrLesson(data.lesson.id);
          }
          setCurrChapterId(cid);
          console.log('next chapter', cid, data.lesson.id);
        }
      } else {
        const data = getCurrElementStatic(nextTree);
        if (!data) {
          return;
        }

        if (data.catalog) {
          navigate(`/newchat/${data.catalog.id}`);
        }
      }
    })();
  }, [hasLogin, cid, initialized]);

  useEffect(() => {
    updateSelectedLesson(lessonId);
  }, [lessonId]);

  const onLoginModalClose = async () => {
    setLoginModalOpen(false);
    await loadData();
  };

  const onLessonUpdate = (val) => {
    updateChapter(val.id, val);
  };

  const onGoChapter = (id) => {
    navigate(`/newchat/${id}`);
  };

  const onPurchased = () => {
    reloadTree();
  };

  const onGoToSetting = () => {
    setShowUserSettings(true);
  };

  const onLessonSelect = ({ id }) => {
    const chapter = getChapterByLesson(id);
    if (!chapter) {
      return;
    }

    changeCurrLesson(id);
    setTimeout(() => {
      if (chapter.id !== currChapterId) {
        navigate(`/newchat/${chapter.id}`);
      }
    }, 0);
  };

  return (
    <div className={classNames(styles.newChatPage)}>
      <AppContext.Provider
        value={{ frameLayout, hasLogin, userInfo, theme: '' }}
      >
        <Skeleton
          style={{ width: '100%', height: '100%' }}
          loading={!initialized}
          paragraph={true}
          rows={10}
        >
          <NavDrawer
            onLoginClick={() => setLoginModalOpen(true)}
            lessonTree={tree}
            onChapterCollapse={toggleCollapse}
            onLessonSelect={onLessonSelect}
            onGoToSetting={onGoToSetting}
            onTryLessonSelect={onTryLessonSelect}
          />
          {
            <ChatUi
              chapterId={currChapterId}
              lessonUpdate={onLessonUpdate}
              onGoChapter={onGoChapter}
              onPurchased={onPurchased}
              showUserSettings={showUserSettings}
              onUserSettingsClose={() => setShowUserSettings(false)}
            />
          }
        </Skeleton>
        {loginModalOpen && (
          <LoginModal
            open={loginModalOpen}
            onClose={onLoginModalClose}
            destroyOnClose={true}
          />
        )}
        {initialized && <TrackingVisit />}
      </AppContext.Provider>
    </div>
  );
};

export default NewChatPage;
