import styles from './NavHeader.module.scss';
import classNames from 'classnames';
import { memo } from 'react';
import LogoWithText from 'Components/logo/LogoWithText.jsx';
import { useCallback } from 'react';
import { useTracking, EVENT_NAMES } from 'common/hooks/useTracking.js';

export const NavHeader = ({
  showCollapseBtn = true,
  isCollapse = false,
  showCloseBtn = false,
  onToggle = (isCollapse) => {},
  onClose = () => {},
}) => {
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
        styles.navHeader,
        isCollapse ? styles.collapse : ''
      )}
    >
      <div className={styles.logoArea} onClick={onLogoAreaClick}>
        {!isCollapse && <LogoWithText direction="row" size={30} />}
      </div>

      {showCollapseBtn && (
        <div
          className={styles.actionBtn}
          onClick={onToggleButtonClick}
        >
          <img
            src={require('@Assets/newchat/light/icon16-expand.png')}
            alt="展开/折叠"
            className={classNames(styles.icon)}
          />
        </div>
      )}
      {isCollapse && <LogoWithText direction="col" size={30} />}
      {showCloseBtn && (
        <div className={styles.actionBtn} onClick={onClose}>
          X
        </div>
      )}
    </div>
  );
};

export default memo(NavHeader);
