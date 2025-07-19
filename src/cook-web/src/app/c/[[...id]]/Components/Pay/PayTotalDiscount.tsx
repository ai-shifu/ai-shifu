import styles from './PayTotalDiscount.module.scss';
import { memo } from 'react';
import { CircleAlertIcon } from 'lucide-react';

export const PayTotalDiscount = ({ discount }) => {
  const onDescIconClick = () => {
    // alert('onDescIconClick');
  };

  return (
    <div className={styles.payTotalDiscount}>
      <div>已节省：</div>
      <div>{'￥'}{discount || '0.00'}</div>{' '}
      <CircleAlertIcon
        className={styles.descIcon}
        onClick={onDescIconClick}
      />
    </div>
  );
};

export default memo(PayTotalDiscount);
