import { memo } from 'react';
import DOMPurify from 'dompurify';
import styles from './ActiveMessage.module.scss';
import { shifu } from '../config/config';
import ToPayButton from './ToPayButton';
import { useCourseStore } from '@/c-store/useCourseStore';
import { useShallow } from 'zustand/react/shallow';

const ActiveMessage = ({
  msg = '',
  action = '',
  recordId = '',
  button = '',
}) => {
  const { openPayModal } = useCourseStore(
    useShallow(state => ({ openPayModal: state.openPayModal })),
  );
  const _onButtonClick = () => {
    openPayModal({
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
            <span
              dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(msg) }}
            ></span>{' '}
            {button && (
              <ToPayButton onClick={_onButtonClick}>{button}</ToPayButton>
            )}
          </div>
        </div>
      </div>
    </>
  );
};

export default memo(ActiveMessage);
