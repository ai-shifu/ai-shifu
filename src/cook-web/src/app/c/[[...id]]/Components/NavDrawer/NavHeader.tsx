import styles from './NavHeader.module.scss';

import clsx from 'clsx';
import { memo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import Image from 'next/image';

import LogoWithText from '@/c-components/logo/LogoWithText';
import { useTracking, EVENT_NAMES } from '@/c-common/hooks/useTracking';

import imgExpand from '@/c-assets/newchat/light/icon16-expand.png';
import { PanelLeft } from 'lucide-react';

export const NavHeader = ({
  className = '',
  showCollapseBtn = true,
  isCollapse = false,
  showCloseBtn = false,
  onToggle,
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
      className={clsx(
        className,
        styles.navHeader,
        isCollapse ? styles.collapse : '',
        mobileStyle ? styles.mobile : '',
      )}
    >
      <div
        className={styles.logoArea}
        onClick={onLogoAreaClick}
      >
        <LogoWithText
          direction={isCollapse ? 'col' : 'row'}
          size={30}
        />
      </div>

      {showCollapseBtn && (
        <div
          className={styles.actionBtn}
          onClick={onToggleButtonClick}
          style={{ cursor: 'pointer', zIndex: 10 }}
        >
          <PanelLeft className={styles.icon} size={16} />
        </div>
      )}
      {showCloseBtn && (
        <div
          className={styles.actionBtn}
          onClick={onClose}
        >
          X
        </div>
      )}
    </div>
  );
};

export default memo(NavHeader);
