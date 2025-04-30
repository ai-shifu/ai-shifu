import { memo } from 'react';
import { Button } from 'antd';
import { TrophyTwoTone } from '@ant-design/icons';
import MainButton from 'ShiNiang/components/MainButton';
import styles from './OrderPromotePopoverContent.module.scss';
import classNames from 'classnames';

const OrderPromotePopoverContent = ({
  payload,
  onCancelButtonClick,
  onOkButtonClick,
  className,
}) => {
  return (
    <div className={classNames(styles.orderPromotePopoverContent, className)}>
      <div className={styles.leftColumn}>
        <TrophyTwoTone style={{ fontSize: '1.5em' }} twoToneColor="#E99D42" />
      </div>
      <div className={styles.rightColumn}>
        <div className={styles.descRow1}>{payload.pop_up_title}</div>
        <div className={styles.descRow2}>{payload.pop_up_content}</div>
        <div className={styles.buttonRow}>
          <Button
            type="default"
            onClick={onCancelButtonClick}
            style={{ height: 26 }}
          >
            {payload.pop_up_cancel_text}
          </Button>
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
