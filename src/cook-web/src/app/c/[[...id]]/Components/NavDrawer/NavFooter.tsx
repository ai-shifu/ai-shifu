import styles from './NavFooter.module.scss';

import clsx from 'clsx';
import { memo, forwardRef, useImperativeHandle, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/store';

import { Avatar, AvatarImage } from '@/components/ui/Avatar';
import { ChevronsUpDown, ChevronsDownUp } from 'lucide-react';
import imgUser from '@/c-assets/newchat/light/user.png';

export const NavFooter = forwardRef(
  // @ts-expect-error EXPECT
  ({ onClick, isCollapse = false, isMenuOpen = false }, ref) => {
  const { t } = useTranslation();

  const userInfo = useUserStore(state => state.userInfo);
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  const avatar = userInfo?.avatar || 'https://github.com/shadcn.png';
  const htmlRef = useRef(null);

  const containElement = elem => {
    // @ts-expect-error EXPECT
    return htmlRef.current && htmlRef.current.contains(elem);
  };
  useImperativeHandle(ref, () => ({
    containElement,
  }));

  const ToggleIcon = isMenuOpen ? ChevronsDownUp : ChevronsUpDown;

  return (
    <div
      className={clsx(styles.navFooter, isCollapse ? styles.collapse : '')}
      onClick={onClick}
      ref={htmlRef}
    >
      <div className={styles.userSection}>
        <div className={styles.userInfo}>
          <Avatar className='w-8 h-8'>
            <AvatarImage src={avatar} />
          </Avatar>
          <div className={styles.userName}>
            {isLoggedIn
              ? userInfo?.name || t('module.user.defaultUserName')
              : t('module.user.notLogin')}
          </div>
        </div>
        <ToggleIcon
          size={16}
          color='#0A0A0A'
        />
      </div>
    </div>
  );
});

NavFooter.displayName = 'NavFooter';
export default memo(NavFooter);
