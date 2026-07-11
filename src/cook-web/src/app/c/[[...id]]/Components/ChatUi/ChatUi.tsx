'use client';

import styles from './ChatUi.module.scss';

import { memo, useCallback, useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { cn } from '@/lib/utils';
import { useShallow } from 'zustand/react/shallow';
import { useTranslation } from 'react-i18next';

import UserSettings from '../Settings/UserSettings';
import { FRAME_LAYOUT_MOBILE } from '@/c-constants/uiConstants';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useCourseStore, useUiLayoutStore } from '@/c-store';
import MarkdownFlowLink from '@/components/ui/MarkdownFlowLink';
import type { ListenMobileViewModeChangeHandler } from './listenModeTypes';
import CourseHeaderSummary from '../CourseHeaderSummary';
import LearningModeSwitch from '../LearningModeSwitch';
import PreviewHeaderBanner from '../PreviewHeaderBanner';
import LessonUpdateNotice from '../LessonUpdateNotice';

const ChatComponents = dynamic(() => import('./NewChatComp'), {
  ssr: false,
});

interface ChatUiProps {
  chapterId: string;
  lessonId?: string;
  lessonUpdate: (val: any) => void;
  onGoChapter: (id: any) => void;
  onPurchased: () => void;
  lessonTitle?: string;
  lessonStatus?: string;
  lessonHasContentUpdate?: boolean;
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
  onLessonUpdateNoticeVisibilityChange?: (visible: boolean) => void;
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
  lessonHasContentUpdate = false,
  showUserSettings = true,
  userSettingBasicInfo = false,
  onUserSettingsClose = () => {},
  chapterUpdate,
  updateSelectedLesson,
  getNextLessonId,
  isNavOpen = false,
  onListenMobileViewModeChange,
  showGenerateBtn = false,
  onLessonUpdateNoticeVisibilityChange,
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
  const showModeToggle = showLearningModeToggle;
  const isListenMode = learningMode === 'listen';
  const isClassroomMode = learningMode === 'classroom';
  const isSlideMode = isListenMode || isClassroomMode;
  const showHeader = frameLayout !== FRAME_LAYOUT_MOBILE;
  const footerSeparator = String.fromCharCode(124);
  const [isListenPlayerVisible, setIsListenPlayerVisible] = useState(false);
  const [showLessonUpdateNoticeInHeader, setShowLessonUpdateNoticeInHeader] =
    useState(false);

  const handleLessonUpdateNoticeVisibilityChange = useCallback(
    (visible: boolean) => {
      setShowLessonUpdateNoticeInHeader(visible);
      onLessonUpdateNoticeVisibilityChange?.(visible);
    },
    [onLessonUpdateNoticeVisibilityChange],
  );

  useEffect(() => {
    if (!isSlideMode) {
      setIsListenPlayerVisible(false);
    }
  }, [isSlideMode]);

  useEffect(() => {
    setShowLessonUpdateNoticeInHeader(false);
    onLessonUpdateNoticeVisibilityChange?.(false);
  }, [lessonId, onLessonUpdateNoticeVisibilityChange]);

  useEffect(
    () => () => {
      onLessonUpdateNoticeVisibilityChange?.(false);
    },
    [onLessonUpdateNoticeVisibilityChange],
  );

  return (
    <div
      className={cn(
        styles.ChatUi,
        frameLayout === FRAME_LAYOUT_MOBILE ? styles.mobile : '',
        previewMode && frameLayout !== FRAME_LAYOUT_MOBILE
          ? styles.previewModeDesktop
          : '',
        isSlideMode ? styles.listenMode : '',
        isClassroomMode ? styles.classroomMode : '',
        isListenMode && isListenPlayerVisible
          ? styles.listenModeWithPlayer
          : '',
        isSlideMode && !isListenPlayerVisible
          ? styles.listenModeWithoutPlayer
          : '',
        hideMobileFooter ? styles.hideMobileFooter : '',
      )}
    >
      {
        showHeader ? (
          <div
            className={cn(
              styles.header,
              previewMode ? styles.previewHeader : '',
            )}
          >
            {previewMode ? (
              <PreviewHeaderBanner className={styles.previewHeaderBanner} />
            ) : null}
            <div className={styles.headerMain}>
              <div className={styles.headerContent}>
                <CourseHeaderSummary
                  courseAvatar={courseAvatar}
                  courseName={courseName}
                  className={styles.courseSummary}
                  titleClassName={styles.courseSummaryTitle}
                />
              </div>
              {showLessonUpdateNoticeInHeader ? (
                <div className={styles.lessonUpdateNoticeTarget}>
                  <LessonUpdateNotice
                    chapterId={chapterId}
                    lessonId={lessonId}
                    lessonTitle={lessonTitle}
                  />
                </div>
              ) : null}
              {showModeToggle ? (
                <div className={styles.headerActions}>
                  <LearningModeSwitch size='desktop' />
                </div>
              ) : null}
            </div>
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
          lessonHasContentUpdate={lessonHasContentUpdate}
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
          onLessonUpdateNoticeVisibilityChange={
            handleLessonUpdateNoticeVisibilityChange
          }
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
