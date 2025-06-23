import styles from './TrialNodeBottomArea.module.scss';
import { memo, useEffect, useRef, useCallback, useState } from 'react';
import { shifu } from '@/c-service/Shifu';

export const TRAIL_NODE_POSITION = {
  NORMAL: 'normal',
  STICK_TOP: 'stickTop',
  STICK_BOTTOM: 'stickBottom',
};

const TrialNodeBottomArea = ({
  containerScrollTop = 0,
  containerHeight = 0,
  payload,
  onNodePositionChange,
}) => {
  const [offsetToScroller, setOffsetToScroller] = useState(0);
  const normalAreaRef = useRef(null);
  const [currHeight, setCurrHeight] = useState(0);
  const [nodePosition, setNodePosition] = useState(TRAIL_NODE_POSITION.NORMAL);

  const getTrialNodeAreaControl = useCallback(() => {
    const Control = shifu.getControl(shifu.ControlTypes.TRIAL_NODE_BOTTOM_AREA);

    return Control ? <Control payload={payload} /> : <>non</>;
  }, [payload]);

  const isStickTop = useCallback(() => {
    return containerHeight > 0 && containerScrollTop > offsetToScroller;
  }, [containerHeight, containerScrollTop, offsetToScroller]);

  const isStickBottom = useCallback( () => {
    return (
      !isStickTop() && containerHeight > 0 &&
      offsetToScroller + currHeight > containerScrollTop + containerHeight
    );
  }, [containerHeight, containerScrollTop, currHeight, isStickTop, offsetToScroller]);

  useEffect(() => {
    if (normalAreaRef.current) {
      let position = TRAIL_NODE_POSITION.NORMAL;

      setOffsetToScroller(normalAreaRef.current.offsetTop);
      setCurrHeight(normalAreaRef.current.clientHeight);

      if (isStickTop()) {
        position = TRAIL_NODE_POSITION.STICK_TOP;
      } else if (isStickBottom()) {
        position = TRAIL_NODE_POSITION.STICK_BOTTOM;
      }

      if (position !== nodePosition) {
        setNodePosition(position);
        onNodePositionChange?.(position);
      }
    }
  }, [containerHeight, containerScrollTop, isStickBottom, isStickTop, nodePosition, onNodePositionChange]);

  return (
    <>
      <div className={styles.normalArea} ref={normalAreaRef}>
        {getTrialNodeAreaControl()}
      </div>
    </>
  );
};

export default memo(TrialNodeBottomArea);
