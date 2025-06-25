import { memo } from 'react';
import { Button } from '@/components/ui/button';
import { TrophyIcon } from 'lucide-react';
import MainButton from './MainButton';
import styles from './OrderPromotePopoverContent.module.scss';
import classNames from 'classnames';

const OrderPromotePopoverContent = ({ payload, onCancelButtonClick, onOkButtonClick, className }) => {
  return (
    <div className={classNames(styles.orderPromotePopoverContent, className)}>
      <div className={styles.leftColumn}>
        <TrophyIcon className='text-amber-400 text-2xl' />
      </div>
      <div className={styles.rightColumn}>
        <div className={styles.descRow1}>{payload.pop_up_title}</div>
        <div className={styles.descRow2}>{payload.pop_up_content}</div>
        <div className={styles.buttonRow}>
          <Button 
            onClick={onCancelButtonClick} 
            style={{ height: 26 }}>
            {payload.pop_up_cancel_text}
          </Button>
          {/* @ts-expect-error EXPECT */}
          <MainButton
            className={styles.payBtn}
            onClick={onOkButtonClick}
            shape="default"
            height={26}
          >
            {payload.pop_up_confirm_text}
          </MainButton>
        </div>
      </div>
    </div>
  );
};

export default memo(OrderPromotePopoverContent);
