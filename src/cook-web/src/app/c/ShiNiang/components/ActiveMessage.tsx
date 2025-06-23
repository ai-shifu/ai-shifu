import { memo } from 'react';
import styles from './ActiveMessage.module.scss';
import { shifu } from '../config/config';
import ToPayButton from './ToPayButton';

const ActiveMessage = ({
  msg = '',
  action = '',
  recordId = '',
  button = '',
}) => {
  const _onButtonClick = () => {
    shifu.payTools.openPay({
      type: 'active',
      payload: {
        action,
        recordId,
      },
    });
  };

  return (
    <>
      <div className={styles.activeContainer}>
        <div className={styles.activeWrapper}>
          <div>
            <span dangerouslySetInnerHTML={{ __html: msg }}></span>{' '}
            {button && <ToPayButton onClick={_onButtonClick}>{button}</ToPayButton>}
          </div>
        </div>
      </div>
    </>
  );
};

export default memo(ActiveMessage);
