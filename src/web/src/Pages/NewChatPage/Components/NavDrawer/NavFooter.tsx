import classNames from 'classnames';
import { memo, forwardRef, useImperativeHandle, useRef } from 'react';
import { Avatar } from 'antd';
import styles from './NavFooter.module.scss';
import userIcon from 'Assets/newchat/light/user.png';
import { useUserStore } from 'stores/useUserStore';
import { useTranslation } from 'react-i18next';

export const NavFooter = forwardRef(({ onClick, isCollapse = false }, ref) => {
  const { t } = useTranslation();
  const { hasLogin, userInfo } = useUserStore((state) => state);
  const avatar = userInfo?.avatar || userIcon;
  const htmlRef = useRef(null);

  const containElement = (elem) => {
    return htmlRef.current && htmlRef.current.contains(elem);
  };
  useImperativeHandle(ref, () => ({
    containElement,
  }));

  return (
    <div
      className={classNames(
        styles.navFooter,
        isCollapse ? styles.collapse : '',
      )}
      onClick={onClick}
      ref={htmlRef}
    >
      <div className={styles.userSection}>
        <Avatar className={styles.avatar} src={avatar} size={32} />
        <div className={styles.userName}>
          {hasLogin
            ? userInfo?.name || t('user.defaultUserName')
            : t('user.notLogin')}
        </div>
      </div>
    </div>
  );
});

export default memo(NavFooter);
