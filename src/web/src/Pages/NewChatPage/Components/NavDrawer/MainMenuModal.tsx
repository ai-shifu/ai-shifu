import { memo, useRef } from 'react';
import { Dropdown, Modal } from 'antd';
import { useShallow } from 'zustand/react/shallow';
import classNames from 'classnames';
import styles from './MainMenuModal.module.scss';
import PopupModal from 'Components/PopupModal';
import { useTranslation } from 'react-i18next';
import { languages } from 'Service/constants';
import { useUserStore } from 'stores/useUserStore';
import { DownOutlined } from '@ant-design/icons';
import { shifu } from 'Service/Shifu';
import { getUserProfile, updateUserProfile } from 'Api/user';
import { LANGUAGE_DICT } from 'constants/userConstants';
import { useTracking, EVENT_NAMES } from 'common/hooks/useTracking';

const MainMenuModal = ({
  open,
  onClose = () => {},
  style = {},
  mobileStyle = false,
  className = '',
  onBasicInfoClick,
  onPersonalInfoClick,
}) => {
  const htmlRef = useRef(null);
  const { hasLogin, logout } = useUserStore(
    useShallow((state) => ({
      logout: state.logout,
      hasLogin: state.hasLogin,
    })),
  );

  const { i18n, t } = useTranslation();
  const languageDrowdownContainer = (triggerNode) => {
    if (htmlRef.current) {
      return htmlRef.current;
    }

    return triggerNode;
  };

  const { trackEvent } = useTracking();

  const languageDrowdownMeus = {
    items: languages.map((lang) => ({
      key: lang.value,
      label: lang.label,
    })),
    onClick: async ({ key }) => {
      const languageData = LANGUAGE_DICT[key];

      if (languageData) {
        const { data } = await getUserProfile();
        const languageSetting = data.find((item) => item.key === 'language');
        if (languageSetting) {
          languageSetting.value = languageData;
          await updateUserProfile(data);
        }
      }
      i18n.changeLanguage(key);
    },
  };

  const onUserInfoClick = () => {
    trackEvent(EVENT_NAMES.USER_MENU_BASIC_INFO, {});
    if (!hasLogin) {
      trackEvent(EVENT_NAMES.POP_LOGIN, { from: 'user_menu' });
      shifu.loginTools.openLogin();
      return;
    }

    onBasicInfoClick?.();
  };

  const _onPersonalInfoClick = () => {
    trackEvent(EVENT_NAMES.USER_MENU_PERSONALIZED, {});
    if (!hasLogin) {
      trackEvent(EVENT_NAMES.POP_LOGIN, { from: 'user_menu' });
      shifu.loginTools.openLogin();
      return;
    }

    onPersonalInfoClick?.();
  };

  const onLoginClick = () => {
    shifu.loginTools.openLogin();
  };

  const onLogoutClick = async () => {
    await Modal.confirm({
      title: t('user.confirmLogoutTitle'),
      content: t('user.confirmLogoutContent'),
      onOk: async () => {
        await logout();
      },
    });
  };

  return (
    <PopupModal
      open={open}
      onClose={onClose}
      wrapStyle={{ ...style }}
      className={classNames(
        className,
        styles.mainMenuModalWrapper,
        mobileStyle && styles.mobile,
      )}
    >
      <div className={styles.mainMenuModal} ref={htmlRef}>
        <div className={styles.mainMenuModalRow} onClick={onUserInfoClick}>
          <img
            className={styles.rowIcon}
            src={require('@Assets/newchat/light/userInfo.png')}
            alt=""
          />
          <div className={styles.rowTitle}>
            {t('menus.navigationMenus.basicInfo')}
          </div>
        </div>
        <div className={styles.mainMenuModalRow} onClick={_onPersonalInfoClick}>
          <img
            className={styles.rowIcon}
            src={require('@Assets/newchat/light/personal.png')}
            alt=""
          />
          <div className={styles.rowTitle}>
            {t('menus.navigationMenus.personalInfo')}
          </div>
        </div>

        <div className={styles.languageRow}>
          <div
            className={classNames(
              styles.mainMenuModalRow,
              styles.languageRowInner,
            )}
          >
            <div className={styles.languageRowLeft}>
              <img
                className={styles.rowIcon}
                src={require('@Assets/newchat/light/multiLanguage.png')}
                alt=""
              />
              <div className={styles.rowTitle}>
                {t('menus.navigationMenus.language')}
              </div>
            </div>
            <div className={styles.languageRowRight}>
              <Dropdown
                getPopupContainer={languageDrowdownContainer}
                menu={languageDrowdownMeus}
              >
                <div
                  onClick={(e) => {
                    e.preventDefault();
                  }}
                >
                  {languages.find((lang) => lang.value === i18n.language)
                    ?.label || '请选择'}{' '}
                  {<DownOutlined className={style.langDownIcon} />}
                </div>
              </Dropdown>
            </div>
          </div>
        </div>
        {!hasLogin ? (
          <div className={styles.mainMenuModalRow} onClick={onLoginClick}>
            <img
              className={styles.rowIcon}
              src={require('@Assets/newchat/light/signin.png')}
              alt=""
            />
            <div className={styles.rowTitle}>{t('user.login')}</div>
          </div>
        ) : (
          <div className={styles.mainMenuModalRow} onClick={onLogoutClick}>
            <img
              className={styles.rowIcon}
              src={require('@Assets/newchat/light/signin.png')}
              alt=""
            />
            <div className={styles.rowTitle}>{t('user.logout')}</div>
          </div>
        )}
      </div>
    </PopupModal>
  );
};

export default memo(MainMenuModal);
