import styles from './NavBody.module.scss';
import LogoCircle from '@Components/logo/LogoCircle';
import { productName, slogan } from '@constants/productConstants';
import MainButton from '@Components/MainButton.jsx';

export const NavBody = ({ 
  onLoginClick = () => {},
}) => {
  return (<div className={styles.navBody}>
    <LogoCircle />
    <div className={styles.productName}>{productName}</div>
    <div className={styles.slogan}>{slogan}</div>
    <div className={styles.btnWrapper}>
      <MainButton width={185} onClick={() => onLoginClick?.()}>登录/注册</MainButton>
    </div>
  </div>)
}

export default NavBody;
