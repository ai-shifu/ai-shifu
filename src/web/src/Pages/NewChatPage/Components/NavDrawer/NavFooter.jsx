import { forwardRef, useImperativeHandle, useRef } from 'react';
import styles from  './NavFooter.module.scss';
import classNames from 'classnames';
import { memo } from 'react';

import settingsIcon from 'Assets/newchat/light/settings-2x.png';
import themeIcon from 'Assets/newchat/light/icon16-theme.png';
import filingIcon from 'Assets/newchat/light/icon16-filing.png';

import { useTranslation } from 'react-i18next';


export const NavFooter = forwardRef(({
  isCollapse = false,
  onFilingClick = () => {},
  onThemeClick = () => {},
  onSettingsClick = () => {},
}, ref) => {
  const { t } = useTranslation();
  const fillBtnRef = useRef(null);
  const themeBtnRef = useRef(null);
  const settingBtnRef = useRef(null);

  const containElement = (elem) => {
    return (fillBtnRef.current && fillBtnRef.current.contains(elem))
    || (themeBtnRef.current && themeBtnRef.current.contains(elem))
    || (settingBtnRef.current && settingBtnRef.current.contains(elem));
  }


  useImperativeHandle(ref, () => ({
    containElement,
  }));

  return (<div className={classNames(styles.navFooter, isCollapse ? styles.collapse : '') }>
    <div className={styles.settingBtn} onClick={onFilingClick} ref={fillBtnRef} >
      <img src={filingIcon} className={styles.icon} alt={t('navigation.filing')} />
      <div className={styles.btnText}>{t('navigation.filing')}</div>
    </div>
    <div className={styles.settingBtn} onClick={onThemeClick} ref={themeBtnRef}>
      <img src={themeIcon} className={styles.icon} alt={t('navigation.skin')} />
      <div className={styles.btnText}>{t('navigation.skin')}</div>
    </div>
    <div className={styles.settingBtn} onClick={onSettingsClick} ref={settingBtnRef}>
      <img src={settingsIcon} className={styles.icon} alt={t('navigation.settings')} />
      <div className={styles.btnText}>{t('navigation.settings')}</div>
    </div>

  </div>);
});

export default memo(NavFooter);
