import { AppContext } from 'Components/AppContext';
import { useContext } from 'react';
import ChatComponents from './ChatComponents';
import styles from './ChatUi.module.scss';
import UserSettings from '../Settings/UserSettings';
import { FRAME_LAYOUT_MOBILE } from 'constants/uiConstants';
import classNames from 'classnames';
import { memo } from 'react';
import GlobalInfoButton from './GlobalInfoButton';
import { useSystemStore } from 'stores/useSystemStore';
import { useShallow } from 'zustand/react/shallow';
import { useTranslation } from 'react-i18next';

/**
 * 聊天区的整体画布
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
}) => {
  const { frameLayout } = useContext(AppContext);
  const { skip, updateSkip, previewMode } = useSystemStore(
    useShallow((state) => ({
      skip: state.skip,
      updateSkip: state.updateSkip,
      previewMode: state.previewMode
    }))
  );
  const { t } = useTranslation();

  const handlePreviewModeClick = () => {
    updateSkip(!skip);
  };

  return (
    <div
      className={classNames(
        styles.ChatUi,
        frameLayout === FRAME_LAYOUT_MOBILE ? styles.mobile : ''
      )}
    >
      {
        <ChatComponents
          chapterId={chapterId}
          lessonId={lessonId}
          lessonUpdate={lessonUpdate}
          onGoChapter={onGoChapter}
          className={styles.chatComponents}
          onPurchased={onPurchased}
          onMobileSettingClick={onMobileSettingClick}
          chapterUpdate={chapterUpdate}
          updateSelectedLesson={updateSelectedLesson}
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

      <GlobalInfoButton className={styles.globalInfoButton} />
      {previewMode && (
        <div className={styles.previewMode}>
          <button
            className={classNames(styles.previewModeButton, { [styles.active]: skip })}
            onClick={handlePreviewModeClick}
          >
            {skip ? t('chat.stopAutoSkip') : t('chat.startAutoSkip')}
          </button>
        </div>
      )}
    </div>
  );
};

export default memo(ChatUi);
