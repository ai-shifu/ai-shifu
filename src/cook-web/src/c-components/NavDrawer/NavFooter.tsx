import styles from './NavFooter.module.scss';

import clsx from 'clsx';
import {
  memo,
  forwardRef,
  useImperativeHandle,
  useRef,
  type MouseEventHandler,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '@/store';
import { ChevronsUpDown, ChevronsDownUp } from 'lucide-react';

export type NavFooterHandle = {
  containElement: (elem: EventTarget | null) => boolean;
};

type NavFooterProps = {
  onClick?: MouseEventHandler<HTMLDivElement>;
  isCollapse?: boolean;
  isMenuOpen?: boolean;
};

export const NavFooter = forwardRef<NavFooterHandle, NavFooterProps>(
  ({ onClick, isCollapse = false, isMenuOpen = false }, ref) => {
    const { t } = useTranslation();

    const userInfo = useUserStore(state => state.userInfo);
    const isLoggedIn = useUserStore(state => state.isLoggedIn);
    const htmlRef = useRef<HTMLDivElement | null>(null);

    const containElement = (elem: EventTarget | null) => {
      return Boolean(elem instanceof Node && htmlRef.current?.contains(elem));
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
  },
);

NavFooter.displayName = 'NavFooter';

export default memo(NavFooter);
