import styles from './MainMenuModal.module.scss';

import { memo, useRef, useState } from 'react';
import { cn } from '@/lib/utils'
import { useShallow } from 'zustand/react/shallow';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import PopupModal from '@/c-components/PopupModal';
import { useTranslation } from 'react-i18next';
import { languages } from '@/c-service/constants';
import { useUserStore } from '@/c-store/useUserStore';

// import { ChevronDown } from 'lucide-react';

import { shifu } from '@/c-service/Shifu';
import { getUserProfile, updateUserProfile } from '@/c-api/user';
import { LANGUAGE_DICT } from '@/c-constants/userConstants';
import { useTracking, EVENT_NAMES } from '@/c-common/hooks/useTracking';

import Image from 'next/image';
import imgUserInfo from '@/c-assets/newchat/light/userInfo.png'
import imgPersonal from '@/c-assets/newchat/light/personal.png'
import imgMultiLanguage from '@/c-assets/newchat/light/multiLanguage.png'
import imgSignIn from '@/c-assets/newchat/light/signin.png'

/**
 * TODO：FIXME
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

  // const languageDrowdownContainer = (triggerNode) => {
  //   if (htmlRef.current) {
  //     return htmlRef.current;
  //   }

  //   return triggerNode;
  // };

  const { trackEvent } = useTracking();

  const languageDrowdownMeus = {
    items: languages.map((lang) => ({
      key: lang.value,
      label: lang.label,
    })),
    onClick: async ({ key }) => {

      const languageData = LANGUAGE_DICT[key];

      if (languageData) {
        // @ts-expect-error EXPECT
        const { data } = await getUserProfile();
        const languageSetting = data.find((item) => item.key === 'language');
        if (languageSetting) {
          languageSetting.value = languageData;
          // @ts-expect-error EXPECT
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

  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false);
  const onLogoutConfirm = async () => {
     await logout();
     setLogoutConfirmOpen(false);
  };

  return (
    <>
       <AlertDialog 
        open={logoutConfirmOpen} 
        onOpenChange={(open) => setLogoutConfirmOpen(open)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              { t('user.confirmLogoutTitle') }
            </AlertDialogTitle>
            <AlertDialogDescription>
              { t('user.confirmLogoutContent') }
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
        className={cn(className, styles.mainMenuModalWrapper, mobileStyle && styles.mobile)}
      >
        <div className={styles.mainMenuModal} ref={htmlRef}>
          <div className={styles.mainMenuModalRow} onClick={onUserInfoClick}>
            <Image
              className={styles.rowIcon}
              width={16}
              height={16}
              src={imgUserInfo.src}
              alt=""
            />
            <div className={styles.rowTitle}>
              {t('menus.navigationMenus.basicInfo')}
            </div>
          </div>
          <div className={styles.mainMenuModalRow} onClick={_onPersonalInfoClick}>
            <Image
              className={styles.rowIcon}
              width={16}
              height={16}
              src={imgPersonal.src}
              alt=""
            />
            <div className={styles.rowTitle}>
              {t('menus.navigationMenus.personalInfo')}
            </div>
          </div>

          <div className={styles.languageRow}>
            <div
              className={cn(
                styles.mainMenuModalRow,
                styles.languageRowInner
              )}
            >
              <div className={styles.languageRowLeft}>
                <Image
                  className={styles.rowIcon}
                  width={16}
                  height={16}
                  src={imgMultiLanguage.src}
                  alt=""
                />
                <div className={styles.rowTitle}>
                  {t('menus.navigationMenus.language')}
                </div>
              </div>
              <div className={styles.languageRowRight}>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline">请选择</Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent className="w-56" align="start">
                    {languageDrowdownMeus.items.map((li) => {
                      return (
                        <DropdownMenuItem key={li.key} onClick={() => {
                          languageDrowdownMeus.onClick({key: li.key})
                        }}>
                          { li.label }
                        </DropdownMenuItem>
                      )
                    })}
                  </DropdownMenuContent>
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
              <Image
                className={styles.rowIcon}
                width={16}
                height={16}
                src={imgSignIn.src}
                alt=""
              />
              <div className={styles.rowTitle}>{t('user.login')}</div>
            </div>
          ) : (
            <div className={styles.mainMenuModalRow} onClick={onLogoutConfirm}>
              <Image
                className={styles.rowIcon}
                width={16}
                height={16}
                src={imgSignIn.src}
                alt=""
              />
              <div className={styles.rowTitle}>{t('user.logout')}</div>
            </div>
          )}
        </div>
      </PopupModal>
    </>
  );
};

export default memo(MainMenuModal);
