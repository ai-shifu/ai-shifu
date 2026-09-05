import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react';

import clsx from 'clsx';
import styles from './PopupModal.module.scss';

import { useCallback } from 'react';

export type PopupModalProps = {
  open?: boolean;
  onClose?: (event: MouseEvent) => void;
  children?: ReactNode;
  style?: CSSProperties;
  wrapStyle?: CSSProperties;
  className?: string;
};

export const PopupModal = ({
  open = false,
  onClose,
  children,
  style,
  wrapStyle,
  className,
}: PopupModalProps) => {
  const popupRef = useRef<HTMLDivElement | null>(null);

  // Close the popup when clicking outside the modal
  const handleClickOutside = useCallback(
    (event: MouseEvent) => {
      if (
        popupRef.current &&
        !popupRef.current.contains(event.target as Node)
      ) {
        // `data-scroll-locked` indicates that another overlay is active, so the menu cannot be closed directly.
        // TODO: Migrate to `shadcn/ui`
        if (!document.body.getAttribute('data-scroll-locked')) {
          onClose?.(event);
        }
      }
    },
    [onClose],
  );

  // Listen for outside click events
  useEffect(() => {
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [handleClickOutside]);

  return (
    <div
      className={clsx(styles.popupModalWrapper, className)}
      style={wrapStyle}
    >
      {open && (
        <div
          style={style}
          className={styles.popupModal}
          ref={popupRef}
        >
          {children}
        </div>
      )}
    </div>
  );
};

export default PopupModal;
