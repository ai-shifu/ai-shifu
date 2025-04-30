import styles from './NavHeader.module.scss';
import classNames from 'classnames';
import { memo } from 'react';
import LogoWithText from 'Components/logo/LogoWithText';
import { useCallback } from 'react';
import { useTracking, EVENT_NAMES } from 'common/hooks/useTracking';
import { useTranslation } from 'react-i18next';

export const NavHeader = ({
  className = '',
  showCollapseBtn = true,
  isCollapse = false,
  showCloseBtn = false,
  onToggle = (isCollapse) => {},
  onClose = () => {},
  mobileStyle = false,
}) => {
  const { t } = useTranslation();
  const { trackEvent } = useTracking();
  const onLogoAreaClick = useCallback(() => {
    trackEvent(EVENT_NAMES.NAV_TOP_LOGO, {});
  }, [trackEvent]);

  const onToggleButtonClick = useCallback(() => {
    if (isCollapse) {
      trackEvent(EVENT_NAMES.NAV_TOP_EXPAND, {});
    } else {
      trackEvent(EVENT_NAMES.NAV_TOP_COLLAPSE, {});
    }
    onToggle?.({ isCollapse: !isCollapse });
  }, [isCollapse, onToggle, trackEvent]);
  return (
    <div
      className={classNames(
        className,
        styles.navHeader,
        isCollapse ? styles.collapse : '',
        mobileStyle ? styles.mobile : '',
      )}
    >
      <div className={styles.logoArea} onClick={onLogoAreaClick}>
        <LogoWithText direction={isCollapse ? 'col' : 'row'} size={30} />
      </div>

      {showCollapseBtn && (
        <div
          className={styles.actionBtn}
          onClick={onToggleButtonClick}
          style={{ cursor: 'pointer', zIndex: 10 }}
        >
          <img
            src={require('@Assets/newchat/light/icon16-expand.png')}
            alt={t('common.expandCollapse')}
            className={classNames(styles.icon)}
          />
        </div>
      )}
      {showCloseBtn && (
        <div className={styles.actionBtn} onClick={onClose}>
          X
        </div>
      )}
    </div>
  );
};

export default memo(NavHeader);
