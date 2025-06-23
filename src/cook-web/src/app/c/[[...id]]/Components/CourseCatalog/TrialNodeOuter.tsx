import { memo, useCallback } from 'react';
import { shifu } from '@/c-service/Shifu';
import styles from './TrialNodeOuter.module.scss';
import { TRAIL_NODE_POSITION } from './TrialNodeBottomArea';

const TrialNodeOuter = ({ nodePosition, payload, containerScrollTop }) => {
  const getTrialNodeAreaControl = useCallback(() => {
    const Control = shifu.getControl(shifu.ControlTypes.TRIAL_NODE_BOTTOM_AREA);

    return Control ? <Control payload={payload} /> : <>non</>;
  }, [payload]);

  const getClassName = useCallback(() => {
    let className = '';

    nodePosition === TRAIL_NODE_POSITION.STICK_TOP &&
      (className = styles.stickTop);
    nodePosition === TRAIL_NODE_POSITION.STICK_BOTTOM &&
      (className = styles.stickBottom);

    return className;
  }, [nodePosition]);

  const getStyle = useCallback(() => {
    if (nodePosition === TRAIL_NODE_POSITION.STICK_TOP) {
      return {
        top: `0px`,
      };
    }

    if (nodePosition === TRAIL_NODE_POSITION.STICK_BOTTOM) {
      return {
        bottom: `0px`,
      };
    }
  }, [nodePosition]);

  return (
    <div className={`${styles.trialNodeOuter} ${getClassName()}`} style={getStyle()}>
      {getTrialNodeAreaControl()}
    </div>
  );
};

export default memo(TrialNodeOuter);
