import { memo } from 'react';
import { AiOutlineExclamationCircle } from 'react-icons/ai';
import styles from './PayTotalDiscount.module.scss';

export const PayTotalDiscount = ({ discount }) => {
  const onDescIconClick = () => {
    // alert('onDescIconClick');
  };

  return (
    <div className={styles.payTotalDiscount}>
      <div>已节省：</div>
      <div>{'￥'}{discount || '0.00'}</div>{' '}
      <AiOutlineExclamationCircle
        className={styles.descIcon}
        onClick={onDescIconClick}
      />
    </div>
  );
};

export default memo(PayTotalDiscount);
