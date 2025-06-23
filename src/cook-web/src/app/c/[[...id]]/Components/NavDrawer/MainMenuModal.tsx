import styles from './MainMenuModal.module.scss';

import { memo, useRef } from 'react';
// import { Dropdown, Modal } from 'antd';
import clsx from 'clsx';
import { useShallow } from 'zustand/react/shallow';
import { DropdownMenu } from '@/components/ui/dropdown-menu';

import PopupModal from '@/c-components/PopupModal';
import { useTranslation } from 'react-i18next';
import { languages } from '@/c-service/constants';
import { useUserStore } from '@/c-store/useUserStore';

import { ChevronDown } from 'lucide-react';

import { shifu } from '@/c-service/Shifu';
import { getUserProfile, updateUserProfile } from '@/c-api/user';
import { LANGUAGE_DICT } from '@/c-constants/userConstants';
import { useTracking, EVENT_NAMES } from '@/c-common/hooks/useTracking';

import imgUserInfo from '@/c-assets/newchat/light/userInfo.png'
import imgPersonal from '@/c-assets/newchat/light/personal.png'
import imgMultiLanguage from '@/c-assets/newchat/light/multiLanguage.png'
import imgSignIn from '@/c-assets/newchat/light/signin.png'

/**
 * TODO：迁移这个组件弹出菜单中列出的页面
 * - 语言切换组件似乎可以直接用 `cook-web` 的
 */


const MainMenuModal = ({
  open,
  onClose = () => {},
  style = {},
  mobileStyle = false,
  className = '',
  onBasicInfoClick,
  onPersonalInfoClick,
}) => {
  const { i18n, t } = useTranslation('translation', { keyPrefix: 'c' });

  const htmlRef = useRef(null);
  const { hasLogin, logout } = useUserStore(
    useShallow((state) => ({
      logout: state.logout,
      hasLogin: state.hasLogin,
    }))
  );

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
      className={clsx(className, styles.mainMenuModalWrapper, mobileStyle && styles.mobile)}
    >
      <div className={styles.mainMenuModal} ref={htmlRef}>
        <div className={styles.mainMenuModalRow} onClick={onUserInfoClick}>
          <img
            className={styles.rowIcon}
            src={imgUserInfo.src}
            alt=""
          />
          <div className={styles.rowTitle}>
            {t('menus.navigationMenus.basicInfo')}
          </div>
        </div>
        <div className={styles.mainMenuModalRow} onClick={_onPersonalInfoClick}>
          <img
            className={styles.rowIcon}
            src={imgPersonal.src}
            alt=""
          />
          <div className={styles.rowTitle}>
            {t('menus.navigationMenus.personalInfo')}
          </div>
        </div>

        <div className={styles.languageRow}>
          <div
            className={clsx(
              styles.mainMenuModalRow,
              styles.languageRowInner
            )}
          >
            <div className={styles.languageRowLeft}>
              <img
                className={styles.rowIcon}
                src={imgMultiLanguage.src}
                alt=""
              />
              <div className={styles.rowTitle}>
                {t('menus.navigationMenus.language')}
              </div>
            </div>
            <div className={styles.languageRowRight}>
              <DropdownMenu>
                {/* TODO: 完成 DropdonMenu 的替换 */}
              </DropdownMenu>
              {/* <Dropdown
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
                  {<ChevronDown className={style.langDownIcon} />}
                </div>
              </Dropdown> */}
            </div>
          </div>
        </div>
        {!hasLogin ? (
          <div className={styles.mainMenuModalRow} onClick={onLoginClick}>
            <img
              className={styles.rowIcon}
              src={imgSignIn.src}
              alt=""
            />
            <div className={styles.rowTitle}>{t('user.login')}</div>
          </div>
        ) : (
          <div className={styles.mainMenuModalRow} onClick={onLogoutClick}>
            <img
              className={styles.rowIcon}
              src={imgSignIn.src}
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
