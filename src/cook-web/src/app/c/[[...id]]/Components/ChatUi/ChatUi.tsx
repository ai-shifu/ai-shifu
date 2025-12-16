import styles from './ChatUi.module.scss';

import { memo } from 'react';
import { cn } from '@/lib/utils';
import { useShallow } from 'zustand/react/shallow';
import { useTranslation } from 'react-i18next';

import ChatComponents from './NewChatComp';
import UserSettings from '../Settings/UserSettings';
import { FRAME_LAYOUT_MOBILE } from '@/c-constants/uiConstants';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useCourseStore, useUiLayoutStore } from '@/c-store';
import { Avatar, AvatarImage } from '@/components/ui/Avatar';

/**
 * Overall canvas for the chat area
 */
export const ChatUi = ({
  chapterId,
  lessonId,
  lessonUpdate,
  onGoChapter,
  onPurchased,
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
  const { previewMode } = useSystemStore(
    useShallow(state => ({
      skip: state.skip,
      updateSkip: state.updateSkip,
      previewMode: state.previewMode,
    })),
  );

  const { courseAvatar, courseName } = useCourseStore(state => state);
  const hideMobileFooter = frameLayout === FRAME_LAYOUT_MOBILE && isNavOpen;

  return (
    <div
      className={cn(
        styles.ChatUi,
        frameLayout === FRAME_LAYOUT_MOBILE ? styles.mobile : '',
        hideMobileFooter ? styles.hideMobileFooter : '',
      )}
    >
      {frameLayout !== FRAME_LAYOUT_MOBILE ? (
        <div className={styles.header}></div>
      ) : (
        <div className={styles.headerMobile}></div>
      )}
      {
        <ChatComponents
          chapterId={chapterId}
          lessonId={lessonId}
          lessonUpdate={lessonUpdate}
          onGoChapter={onGoChapter}
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
          className={styles.UserSettings}
          onHomeClick={onUserSettingsClose}
          onClose={onUserSettingsClose}
          isBasicInfo={userSettingBasicInfo}
        />
      )}

      <div className={styles.footer}>
        <div className={styles.footerContent}>
          <span className={styles.footerText}>
            {t('module.chat.aiGenerated')}
          </span>
          <span className={styles.separator}>|</span>
          <span className={styles.footerText}>
            {t('module.chat.poweredByPrefix')}{' '}
            <a
              href="https://markdownflow.ai/"
              target="_blank"
              rel="noopener noreferrer"
              className={styles.footerLink}
            >
              {t('module.chat.markdownFlow')}
            </a>
            {t('module.chat.poweredBySuffix') && ' '}{t('module.chat.poweredBySuffix')}
          </span>
        </div>
      </div>
    </div>
  );
};

export default memo(ChatUi);
