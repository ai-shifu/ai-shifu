import styles from './MainMenuModal.module.scss';

import { memo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { useShallow } from 'zustand/react/shallow';
import { normalizeLanguage } from '@/i18n';
import { useSystemStore } from '@/c-store/useSystemStore';
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
import { useEnvStore } from '@/c-store/envStore';
import SetPasswordModal from '../Settings/SetPasswordModal';

import Image from 'next/image';
import imgPersonal from '@/c-assets/newchat/light/personal.png';
import imgMultiLanguage from '@/c-assets/newchat/light/multiLanguage.png';
import imgSignIn from '@/c-assets/newchat/light/signin.png';
import { Monitor, BookPlus, KeyRound } from 'lucide-react';

import LanguageSelect from '@/components/language-select';

const MainMenuModal = ({
  open,
  onClose = () => {},
  style = {},
  mobileStyle = false,
  className = '',
  onBasicInfoClick,
  onPersonalInfoClick,
  isAdmin = false,
}) => {
  const { t } = useTranslation();

  const htmlRef = useRef(null);
  const { isLoggedIn, logout, userInfo, refreshUserInfo } = useUserStore(
    useShallow(state => ({
      logout: state.logout,
      isLoggedIn: state.isLoggedIn,
      userInfo: state.userInfo,
      refreshUserInfo: state.refreshUserInfo,
    })),
  );

  const isCreator = userInfo?.is_creator ?? false;
  const loginMethodsEnabled = useEnvStore(state => state.loginMethodsEnabled);
  const isPasswordEnabled = Array.isArray(loginMethodsEnabled)
    ? loginMethodsEnabled.includes('password')
    : false;

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

  const [setPasswordModalOpen, setSetPasswordModalOpen] = useState(false);
  const onSetPasswordClick = (evt: React.MouseEvent) => {
    evt.preventDefault();
    evt.stopPropagation();
    trackEvent(EVENT_NAMES.USER_MENU_SET_PASSWORD, {});
    if (!isLoggedIn) {
      trackEvent(EVENT_NAMES.POP_LOGIN, { from: 'user_menu_set_password' });
      shifu.loginTools.openLogin();
      return;
    }

    setSetPasswordModalOpen(true);
    // Close the user menu to avoid layering with the password modal.
    // @ts-expect-error EXPECT
    onClose?.(evt);
  };

  const onAdminEntryClick = (evt: React.MouseEvent) => {
    evt.preventDefault();
    evt.stopPropagation();
    // Admin console handles login redirect and permission request internally
    window.open('/admin', '_blank');
    // @ts-expect-error EXPECT
    onClose?.(evt);
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

  const updateLanguage = async (language: string) => {
    const normalized = normalizeLanguage(language);
    // Persist preference to backend (best-effort)
    try {
      await api.updateUserInfo({ language: normalized });
    } catch (e) {
      // Non-blocking: UI already switched via LanguageSelect
      console.warn('Failed to persist language preference', e);
    }
    // Update local store so pages relying on userInfo.language react immediately
    useUserStore.getState().updateUserInfo({ language: normalized });
    // Keep system store language in sync for APIs that read it
    try {
      useSystemStore.getState().updateLanguage(normalized);
    } catch {}
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
            <AlertDialogCancel>{t('common.core.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={onLogoutConfirm}>
              {t('common.core.ok')}
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
          {!isAdmin && (
            <>
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
              {isPasswordEnabled ? (
                <div
                  className={cn(styles.mainMenuModalRow, 'px-2.5')}
                  onClick={onSetPasswordClick}
                  title={t('module.settings.password')}
                >
                  <KeyRound
                    className={styles.rowIcon}
                    size={16}
                  />
                  <div className={styles.rowTitle}>
                    {t('module.settings.passwordPlaceholder')}
                  </div>
                </div>
              ) : null}
              <div
                className={cn(styles.mainMenuModalRow, 'px-2.5')}
                onClick={onAdminEntryClick}
              >
                {isCreator ? (
                  <Monitor
                    className={styles.rowIcon}
                    size={16}
                  />
                ) : (
                  <BookPlus
                    className={styles.rowIcon}
                    size={16}
                  />
                )}
                <div className={styles.rowTitle}>
                  {isCreator
                    ? t('component.menus.navigationMenus.adminConsole')
                    : t('component.menus.navigationMenus.createCourse')}
                </div>
              </div>
            </>
          )}

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
      <SetPasswordModal
        open={setPasswordModalOpen}
        onClose={() => setSetPasswordModalOpen(false)}
        onSuccess={refreshUserInfo}
      />
    </>
  );
};

export default memo(MainMenuModal);
