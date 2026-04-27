import styles from './ChatUi.module.scss';

import { memo, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { useShallow } from 'zustand/react/shallow';
import { useTranslation } from 'react-i18next';

import ChatComponents from './NewChatComp';
import UserSettings from '../Settings/UserSettings';
import { FRAME_LAYOUT_MOBILE } from '@/c-constants/uiConstants';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useCourseStore, useUiLayoutStore } from '@/c-store';
import MarkdownFlowLink from '@/components/ui/MarkdownFlowLink';
import type { ListenMobileViewModeChangeHandler } from './listenModeTypes';
import CourseHeaderSummary from '../CourseHeaderSummary';
import LearningModeSwitch from '../LearningModeSwitch';

interface ChatUiProps {
  chapterId: string;
  lessonId?: string;
  lessonUpdate: (val: any) => void;
  onGoChapter: (id: any) => void;
  onPurchased: () => void;
  lessonTitle?: string;
  lessonStatus?: string;
  showUserSettings?: boolean;
  userSettingBasicInfo?: boolean;
  onUserSettingsClose?: () => void;
  onMobileSettingClick?: () => void;
  chapterUpdate: any;
  updateSelectedLesson: any;
  getNextLessonId: any;
  isNavOpen?: boolean;
  onListenMobileViewModeChange?: ListenMobileViewModeChangeHandler;
  showGenerateBtn?: boolean;
}

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
  lessonStatus = '',
  showUserSettings = true,
  userSettingBasicInfo = false,
  onUserSettingsClose = () => {},
  chapterUpdate,
  updateSelectedLesson,
  getNextLessonId,
  isNavOpen = false,
  onListenMobileViewModeChange,
  showGenerateBtn = false,
}: ChatUiProps) => {
  const { t } = useTranslation();
  const { frameLayout } = useUiLayoutStore(state => state);
  const { courseAvatar, courseName } = useCourseStore(
    useShallow(state => ({
      courseAvatar: state.courseAvatar,
      courseName: state.courseName,
    })),
  );
  const { previewMode, learningMode, showLearningModeToggle } = useSystemStore(
    useShallow(state => ({
      skip: state.skip,
      updateSkip: state.updateSkip,
      previewMode: state.previewMode,
      learningMode: state.learningMode,
      showLearningModeToggle: state.showLearningModeToggle,
    })),
  );

  const hideMobileFooter = frameLayout === FRAME_LAYOUT_MOBILE && isNavOpen;
  const showHeader = frameLayout !== FRAME_LAYOUT_MOBILE;
  const showModeToggle = showLearningModeToggle;
  const isListenMode = learningMode === 'listen';
  const footerSeparator = String.fromCharCode(124);
  const [isListenPlayerVisible, setIsListenPlayerVisible] = useState(false);

  useEffect(() => {
    if (!isListenMode) {
      setIsListenPlayerVisible(false);
    }
  }, [isListenMode]);

  return (
    <div
      className={cn(
        styles.ChatUi,
        frameLayout === FRAME_LAYOUT_MOBILE ? styles.mobile : '',
        isListenMode ? styles.listenMode : '',
        isListenMode && isListenPlayerVisible
          ? styles.listenModeWithPlayer
          : '',
        isListenMode && !isListenPlayerVisible
          ? styles.listenModeWithoutPlayer
          : '',
        hideMobileFooter ? styles.hideMobileFooter : '',
      )}
    >
      {
        showHeader ? (
          <div className={styles.header}>
            <div className={styles.headerContent}>
              <CourseHeaderSummary
                courseAvatar={courseAvatar}
                courseName={courseName}
                className={styles.courseSummary}
                titleClassName={styles.courseSummaryTitle}
              />
            </div>
            {showModeToggle ? (
              <div className={styles.headerActions}>
                <LearningModeSwitch size='desktop' />
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
          lessonStatus={lessonStatus}
          className={cn(
            styles.chatComponents,
            showUserSettings ? styles.chatComponentsHidden : '',
          )}
          previewMode={previewMode}
          onPurchased={onPurchased}
          chapterUpdate={chapterUpdate}
          updateSelectedLesson={updateSelectedLesson}
          getNextLessonId={getNextLessonId}
          isNavOpen={isNavOpen}
          onListenMobileViewModeChange={onListenMobileViewModeChange}
          onListenPlayerVisibilityChange={setIsListenPlayerVisible}
          showGenerateBtn={showGenerateBtn}
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
          <span className={styles.separator}>{footerSeparator}</span>
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
