import { AppContext } from 'Components/AppContext.js';
import { useContext } from 'react';
import ChatComponents from './ChatComponents.jsx';
import styles from './ChatUi.module.scss';
import UserSettings from '../Settings/UserSettings.jsx';
import { FRAME_LAYOUT_MOBILE } from 'constants/uiConstants.js';
import classNames from 'classnames';
import { memo } from 'react';
import GlobalInfoButton from './GlobalInfoButton.jsx';

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
    </div>
  );
};

export default memo(ChatUi);
