import styles from './ChatUi.module.scss';

import { memo, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { useShallow } from 'zustand/react/shallow';
import { useTranslation } from 'react-i18next';
import { BookOpen, Headphones } from 'lucide-react';

import ChatComponents from './NewChatComp';
import UserSettings from '../Settings/UserSettings';
import { FRAME_LAYOUT_MOBILE } from '@/c-constants/uiConstants';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useCourseStore, useUiLayoutStore } from '@/c-store';
import { Avatar, AvatarImage } from '@/components/ui/Avatar';
import MarkdownFlowLink from '@/components/ui/MarkdownFlowLink';

/**
 * Overall canvas for the chat area
 */
export const ChatUi = ({
  chapterId,
  lessonId,
  lessonUpdate,
  onGoChapter,
  onPurchased,
  lessonTitle = '',
  showUserSettings = true,
  userSettingBasicInfo = false,
  onUserSettingsClose = () => {},
  onMobileSettingClick = () => {},
  chapterUpdate,
  updateSelectedLesson,
  getNextLessonId,
  isNavOpen = false,
}) => {
  const { t } = useTranslation();
  const { frameLayout } = useUiLayoutStore(state => state);
  const {
    previewMode,
    learningMode,
    updateLearningMode,
    showLearningModeToggle,
  } = useSystemStore(
    useShallow(state => ({
      skip: state.skip,
      updateSkip: state.updateSkip,
      previewMode: state.previewMode,
      learningMode: state.learningMode,
      updateLearningMode: state.updateLearningMode,
      showLearningModeToggle: state.showLearningModeToggle,
    })),
  );

  const { courseAvatar, courseName } = useCourseStore(state => state);
  const hideMobileFooter = frameLayout === FRAME_LAYOUT_MOBILE && isNavOpen;
  const showHeader = frameLayout !== FRAME_LAYOUT_MOBILE;
  const showModeToggle = showLearningModeToggle;

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const root = document.documentElement;
    const updateSafeAreaBottom = () => {
      const viewport = window.visualViewport;
      const viewportHeight = viewport?.height ?? window.innerHeight;
      const viewportOffsetTop = viewport?.offsetTop ?? 0;
      const bottomInset = Math.max(
        0,
        window.innerHeight - viewportHeight - viewportOffsetTop,
      );
      root.style.setProperty(
        '--safe-area-bottom',
        `${Math.round(bottomInset)}px`,
      );
    };

    updateSafeAreaBottom();
    window.addEventListener('resize', updateSafeAreaBottom);
    window.addEventListener('orientationchange', updateSafeAreaBottom);
    window.visualViewport?.addEventListener('resize', updateSafeAreaBottom);
    window.visualViewport?.addEventListener('scroll', updateSafeAreaBottom);

    return () => {
      window.removeEventListener('resize', updateSafeAreaBottom);
      window.removeEventListener('orientationchange', updateSafeAreaBottom);
      window.visualViewport?.removeEventListener('resize', updateSafeAreaBottom);
      window.visualViewport?.removeEventListener('scroll', updateSafeAreaBottom);
      root.style.removeProperty('--safe-area-bottom');
    };
  }, []);

  return (
    <div
      className={cn(
        styles.ChatUi,
        frameLayout === FRAME_LAYOUT_MOBILE ? styles.mobile : '',
        hideMobileFooter ? styles.hideMobileFooter : '',
      )}
    >
      {
        showHeader ? (
          <div className={styles.header}>
            {showModeToggle ? (
              <div className={styles.headerActions}>
                <button
                  type='button'
                  className={cn(
                    styles.modeButton,
                    learningMode === 'listen' ? styles.modeButtonActive : '',
                  )}
                  onClick={() => updateLearningMode('listen')}
                >
                  <Headphones
                    size={16}
                    strokeWidth={2}
                  />
                  <span>听课</span>
                </button>
                <button
                  type='button'
                  className={cn(
                    styles.modeButton,
                    learningMode === 'read' ? styles.modeButtonActive : '',
                  )}
                  onClick={() => updateLearningMode('read')}
                >
                  <BookOpen
                    size={16}
                    strokeWidth={2}
                  />
                  <span>阅读</span>
                </button>
              </div>
            ) : null}
          </div>
        ) : null
        // <div className={styles.headerMobile}></div>
      }
      {
        <ChatComponents
          chapterId={chapterId}
          lessonId={lessonId}
          lessonUpdate={lessonUpdate}
          onGoChapter={onGoChapter}
          lessonTitle={lessonTitle}
          className={cn(
            styles.chatComponents,
            showUserSettings ? styles.chatComponentsHidden : '',
          )}
          previewMode={previewMode}
          onPurchased={onPurchased}
          chapterUpdate={chapterUpdate}
          updateSelectedLesson={updateSelectedLesson}
          getNextLessonId={getNextLessonId}
        />
      }
      {showUserSettings && (
        <UserSettings
          className={cn(styles.UserSettings)}
          onHomeClick={onUserSettingsClose}
          onClose={onUserSettingsClose}
          isBasicInfo={userSettingBasicInfo}
        />
      )}

      <div className={styles.footer}>
        <div
          id='chat-scroll-target'
          className={styles.scrollTarget}
        />
        <div className={styles.footerContent}>
          <span className={styles.footerText}>
            {t('module.chat.aiGenerated')}
          </span>
          <span className={styles.separator}>|</span>
          <span className={styles.footerText}>
            <MarkdownFlowLink
              prefix={t('module.chat.poweredByPrefix')}
              suffix={t('module.chat.poweredBySuffix')}
              linkText={t('module.chat.markdownFlow')}
            />
          </span>
        </div>
      </div>
    </div>
  );
};

export default memo(ChatUi);
