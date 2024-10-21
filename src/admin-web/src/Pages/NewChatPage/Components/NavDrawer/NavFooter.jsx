import styles from  './NavFooter.module.scss';
import { ApartmentOutlined } from '@ant-design/icons';
import classNames from 'classnames';

export const NavFooter = ({
  isCollapse = false,
  onFilingClick = () => {},
  onThemeClick = () => {},
  onSettingsClick = () => {},
}) => {
  const iconStyle = { fontSize: '16px' };
  return (<div className={classNames(styles.navFooter, isCollapse ? styles.collapse : '') }>
    <div className={styles.settingBtn} onClick={onFilingClick} >
      <ApartmentOutlined style={iconStyle} />
      <div className={styles.btnText}>备案</div>
    </div>
    <div className={styles.settingBtn} onClick={onThemeClick}>
      <ApartmentOutlined style={iconStyle} />
      <div className={styles.btnText}>皮肤</div>
    </div>
    <div className={styles.settingBtn} onClick={onSettingsClick}>
      <ApartmentOutlined style={iconStyle} />
      <div className={styles.btnText}>设置</div>
    </div>
  </div>);
}

export default NavFooter;
