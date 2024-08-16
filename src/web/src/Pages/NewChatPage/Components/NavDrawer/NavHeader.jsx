import styles from "./NavHeader.module.scss";
import LogoCircle from "Components/logo/LogoCircle.jsx";
import { productName } from '@constants/productConstants';
import classNames from 'classnames';

export const NavHeader = ({
  showCollapseBtn = true,
  isCollapse = false,
  showCloseBtn = false,
  onToggle = (isCollapse) => {},
  onClose = () => {},
}) => {
  return (
    <div className={classNames(styles.navHeader, isCollapse ? styles.collapse : '')}>
      <div className={styles.logoArea}>
        <LogoCircle size={24} />
        {!isCollapse && <div className={styles.productName}>{productName}</div>}
      </div>
        
      {showCollapseBtn 
        && (<div className={styles.actionBtn} onClick={() => onToggle?.({ isCollapse: !isCollapse })}>
          <img src={require('@Assets/newchat/light/icon16-expand.png')} alt="展开/折叠" className={classNames(styles.icon)} />
        </div>)}
      {showCloseBtn && <div className={styles.actionBtn} onClick={onClose}>X</div>}
      
    </div>
  );
};

export default NavHeader;
