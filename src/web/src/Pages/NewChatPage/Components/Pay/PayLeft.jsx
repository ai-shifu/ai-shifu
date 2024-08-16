import { memo } from 'react';
import LogoWithText from 'Components/logo/LogoWithText.jsx';
import styles from './PayLeft.module.scss';

export const PayLeft = () => {
  return (
    <div className={styles.payLeft}>
      <div className={styles.logoWrapper}>
        <LogoWithText direction="row" color="white" size={40} />
      </div>
      <div className={styles.description}>
        专家把关课程体系，AI 授课个性学习，真人助教答疑
      </div>
      <div className={styles.infoTitle}>跟 AI 学 Python</div>
      <div className={styles.infoLines}>
        <div className={styles.infoLine}>· 编程零基础快速入门 Python</div>
        <div className={styles.infoLine}>· 互动式对话学习，让学习更轻松</div>
        <div className={styles.infoLine}>· 首发特惠，立刻拥有你的 AI 教练</div>
      </div>
    </div>
  );
};

export default memo(PayLeft);
