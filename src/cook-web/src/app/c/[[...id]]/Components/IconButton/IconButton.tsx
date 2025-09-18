import { useState, useRef } from 'react';
import styles from './IconButton.module.scss';
import { useEffect, useCallback } from 'react';

export const IconButton = ({
  icon = '',
  hoverIcon = '',
  activeIcon = '',
  selectedIcon = '',
  width = 36,
  borderRadius = 10,
  selected = false,
  onClick = () => {},
}) => {
  const [isHover, setIsHover] = useState(false);
  const [isActive, setIsActive] = useState(false);
  const topRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onMouseEnter = () => {
      setIsHover(true);
    };

    const onMouseLeave = () => {
      setIsHover(false);
    };

    const onMouseDown = () => {
      setIsActive(true);
    };

    const onMouseUp = () => {
      setIsActive(false);
    };

    const elem = topRef.current;
    // if (elem) {
    //   elem.addEventListener('mouseenter', onMouseEnter);
    //   elem.addEventListener('mouseleave', onMouseLeave);
    //   elem.addEventListener('mousedown', onMouseDown);
    //   elem.addEventListener('mouseup', onMouseUp);
    // }

    return () => {
      elem?.removeEventListener('mouseenter', onMouseEnter);
      elem?.removeEventListener('mouseleave', onMouseLeave);
      elem?.removeEventListener('mousedown', onMouseDown);
      elem?.removeEventListener('mouseup', onMouseUp);
    };
  }, []);

  const genImageSrc = useCallback(() => {
    const baseIcon = selected ? selectedIcon : icon;

    let src = baseIcon;
    if (isHover) {
      src = hoverIcon;
    } else if (isActive) {
      src = activeIcon;
    }

    src = src || icon;

    return src;
  }, [icon, activeIcon, hoverIcon, selectedIcon, isActive, isHover, selected]);

  return (
    <div
      ref={topRef}
      className={styles.IconButton}
      style={{
        width: `${width}px`,
        height: `${width}px`,
        borderRadius: `${borderRadius}px`,
      }}
      onClick={onClick}
    >
      <img src={genImageSrc()} alt="" className={styles.innerIcon} />
    </div>
  );
};

export default IconButton;
