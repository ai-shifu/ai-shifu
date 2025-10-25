import styles from './MainMenuModal.module.scss';

import { memo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { useShallow } from 'zustand/react/shallow';
import i18n from '@/i18n';
import api from '@/api';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/AlertDialog';

import PopupModal from '@/c-components/PopupModal';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/store';
import { shifu } from '@/c-service/Shifu';
import { useTracking, EVENT_NAMES } from '@/c-common/hooks/useTracking';

import Image from 'next/image';
import imgUserInfo from '@/c-assets/newchat/light/userInfo.png';
import imgPersonal from '@/c-assets/newchat/light/personal.png';
import imgMultiLanguage from '@/c-assets/newchat/light/multiLanguage.png';
import imgSignIn from '@/c-assets/newchat/light/signin.png';

import LanguageSelect from '@/components/language-select';

const MainMenuModal = ({
  open,
  onClose = () => {},
  style = {},
  mobileStyle = false,
  className = '',
  onBasicInfoClick,
  onPersonalInfoClick,
}) => {
  const { t } = useTranslation();

  const htmlRef = useRef(null);
  const { isLoggedIn, logout } = useUserStore(
    useShallow(state => ({
      logout: state.logout,
      isLoggedIn: state.isLoggedIn,
    })),
  );

  const { trackEvent } = useTracking();

  const onUserInfoClick = () => {
    trackEvent(EVENT_NAMES.USER_MENU_BASIC_INFO, {});
    if (!isLoggedIn) {
      trackEvent(EVENT_NAMES.POP_LOGIN, { from: 'user_menu' });
      shifu.loginTools.openLogin();
      return;
    }

    onBasicInfoClick?.();
  };

  const _onPersonalInfoClick = () => {
    trackEvent(EVENT_NAMES.USER_MENU_PERSONALIZED, {});
    if (!isLoggedIn) {
      trackEvent(EVENT_NAMES.POP_LOGIN, { from: 'user_menu' });
      shifu.loginTools.openLogin();
      return;
    }

    onPersonalInfoClick?.();
  };

  const onLoginClick = () => {
    shifu.loginTools.openLogin();
  };

  const onLogoutClick = evt => {
    evt.preventDefault();
    evt.stopPropagation();
    setLogoutConfirmOpen(true);
    // @ts-expect-error EXPECT
    onClose?.(evt);
  };

  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false);
  const onLogoutConfirm = async () => {
    try {
      await logout();
      setLogoutConfirmOpen(false);
    } catch (error) {
      console.error('❌ Logout failed:', error);
      setLogoutConfirmOpen(false);
    }
  };

  const normalizeLanguage = (lang: string): string => {
    const supportedLanguages = Object.values(
      i18n.options.fallbackLng || {},
    ).flat();
    const normalizedLang = lang.replace('_', '-');
    if (supportedLanguages.includes(normalizedLang)) {
      return normalizedLang;
    }
    return 'en-US';
  };

  const updateLanguage = (language: string) => {
    // const normalizedLang = normalizeLanguage(language);
    // i18n.changeLanguage(language);
    // console.log('updateLanguage====', language);
    api.updateUserInfo({ language });
  };

  return (
    <>
      <AlertDialog
        open={logoutConfirmOpen}
        onOpenChange={open => setLogoutConfirmOpen(open)}
      >
        <AlertDialogContent className={mobileStyle ? 'w-[80%]' : ''}>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('module.user.confirmLogoutTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('module.user.confirmLogoutContent')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={onLogoutConfirm}>
              确认
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {/* @ts-expect-error EXPECT */}
      <PopupModal
        open={open}
        onClose={onClose}
        wrapStyle={{ ...style }}
        className={cn(
          className,
          styles.mainMenuModalWrapper,
          mobileStyle && styles.mobile,
        )}
      >
        <div
          className={styles.mainMenuModal}
          ref={htmlRef}
        >
          <div
            className={cn(styles.mainMenuModalRow, 'px-2.5')}
            onClick={onUserInfoClick}
          >
            <Image
              className={styles.rowIcon}
              width={16}
              height={16}
              src={imgUserInfo.src}
              alt=''
            />
            <div className={styles.rowTitle}>
              {t('component.menus.navigationMenus.basicInfo')}
            </div>
          </div>
          <div
            className={cn(styles.mainMenuModalRow, 'px-2.5')}
            onClick={_onPersonalInfoClick}
          >
            <Image
              className={styles.rowIcon}
              width={16}
              height={16}
              src={imgPersonal.src}
              alt=''
            />
            <div className={styles.rowTitle}>
              {t('component.menus.navigationMenus.personalInfo')}
            </div>
          </div>

          <div className={styles.languageRow}>
            <div
              className={cn(
                styles.mainMenuModalRow,
                styles.languageRowInner,
                'px-2.5',
              )}
            >
              <div className={styles.languageRowLeft}>
                <Image
                  className={styles.rowIcon}
                  width={16}
                  height={16}
                  src={imgMultiLanguage.src}
                  alt=''
                />
                <div className={styles.rowTitle}>
                  {t('component.menus.navigationMenus.language')}
                </div>
              </div>
              <div className={styles.languageRowRight}>
                <LanguageSelect
                  onSetLanguage={updateLanguage}
                  contentClassName='z-[1001]'
                />
              </div>
            </div>
          </div>
          {!isLoggedIn ? (
            <div
              className={cn(styles.mainMenuModalRow, 'px-2.5')}
              onClick={onLoginClick}
            >
              <Image
                className={styles.rowIcon}
                width={16}
                height={16}
                src={imgSignIn.src}
                alt=''
              />
              <div className={styles.rowTitle}>{t('module.user.login')}</div>
            </div>
          ) : (
            <div
              className={cn(styles.mainMenuModalRow, 'px-2.5')}
              onClick={onLogoutClick}
            >
              <Image
                className={styles.rowIcon}
                width={16}
                height={16}
                src={imgSignIn.src}
                alt=''
              />
              <div className={styles.rowTitle}>{t('module.user.logout')}</div>
            </div>
          )}
        </div>
      </PopupModal>
    </>
  );
};

export default memo(MainMenuModal);
