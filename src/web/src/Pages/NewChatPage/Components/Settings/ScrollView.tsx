import styles from './ScrollView.module.scss';
import { useState } from 'react';
import classNames from 'classnames';

const data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

export const ScrollView = () => {
  const [buffer, setBuffer] = useState(
    data.map((item, index) => ({ key: index, value: item })),
  );
  const [valueIndex, setValueIndex] = useState(10);
  const topOffset = 90;
  const unitLength = 30;

  let lastTime = 0;
  let isScroll = false;
  let scrollDirection = 0;
  const duration = 100 * 1000; // ms

  const onRequestAnimationFrame = (callback) => {
    const now = Date.now();
    if (!isScroll || now - lastTime < duration) {
      requestAnimationFrame(onRequestAnimationFrame);
      return;
    }

    isScroll = false;
    lastTime = now;

    if (scrollDirection) {
      setValueIndex(valueIndex === buffer.length - 1 ? 0 : valueIndex + 1);
    } else {
      setValueIndex(valueIndex === 0 ? buffer.length - 1 : valueIndex - 1);
    }

    requestAnimationFrame(onRequestAnimationFrame);
  };

  requestAnimationFrame(onRequestAnimationFrame);

  const onWheel = (e) => {
    if (e.deltaY > 0) {
      isScroll = true;
      scrollDirection = 1;
    } else {
      isScroll = true;
      scrollDirection = 0;
    }
  };

  const getTranslateY = (index) => {
    const downArrLength = data.length / 2;
    let y = -valueIndex * unitLength;

    if (valueIndex + downArrLength < data.length) {
      if (index >= valueIndex + downArrLength) {
        y = -(data.length * unitLength) + y;
      }
    } else {
      if (index < valueIndex - downArrLength) {
        y = data.length * unitLength + y;
      }
    }

    y += topOffset;
    return y;
  };

  const getZIndex = (index) => {
    return (data.length - Math.abs(index - valueIndex)) * 100;
  };

  return (
    <div className={styles.ScrollView} onWheel={onWheel}>
      {buffer.map((item, index) => {
        return (
          <div
            key={item.key}
            className={classNames(styles.scrollItem)}
            style={{
              transform: `translateY(${getTranslateY(index)}px)`,
              zIndex: getZIndex(index),
            }}
          >
            {item.value}
          </div>
        );
      })}
    </div>
  );
};

export default ScrollView;
