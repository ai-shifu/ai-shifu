import { forwardRef, useImperativeHandle, useRef } from 'react';
import styles from  './NavFooter.module.scss';
import classNames from 'classnames';


export const NavFooter = forwardRef(({
  isCollapse = false,
  onFilingClick = () => {},
  onThemeClick = () => {},
  onSettingsClick = () => {},
}, ref) => {
  const fillBtnRef = useRef(null);
  const themeBtnRef = useRef(null);
  const settingBtnRef = useRef(null);
  
  const containElement = (elem) => {
    return fillBtnRef.current && fillBtnRef.current.contains(elem)
    || themeBtnRef.current && themeBtnRef.current.contains(elem)
    || settingBtnRef.current && settingBtnRef.current.contains(elem);
  }
  
  useImperativeHandle(ref, () => ({
    containElement,
  }));

  return (<div className={classNames(styles.navFooter, isCollapse ? styles.collapse : '') }>
    <div className={styles.settingBtn} onClick={onFilingClick} ref={fillBtnRef} >
      <img src={require('@Assets/newchat/light/icon16-filing.png')} className={styles.icon} alt="备案" />
      <div className={styles.btnText}>备案</div>
    </div>
    <div className={styles.settingBtn} onClick={onThemeClick} ref={themeBtnRef}>
      <img src={require('@Assets/newchat/light/icon16-theme.png')} className={styles.icon} alt="皮肤" />
      <div className={styles.btnText}>皮肤</div>
    </div>
    <div className={styles.settingBtn} onClick={onSettingsClick} ref={settingBtnRef}>
      <img src={require('@Assets/newchat/light/icon16-setting.png')} className={styles.icon} alt="设置" />
      <div className={styles.btnText}>设置</div>
    </div>
  </div>);
});

export default NavFooter;
