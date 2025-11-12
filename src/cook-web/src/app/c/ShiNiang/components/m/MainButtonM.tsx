import styles from './MainButtonM.module.scss';

import {
  memo,
  forwardRef,
  useState,
  type ComponentPropsWithoutRef,
  type MouseEvent,
} from 'react';
import classNames from 'classnames';

import { Button } from '@/components/ui/Button';

type ButtonComponentProps = ComponentPropsWithoutRef<typeof Button>;

type MainButtonMProps = Omit<ButtonComponentProps, 'onClick'> & {
  fill?: 'solid' | 'none';
  shape?: 'rounded' | 'rectangular';
  onClick?: (event: MouseEvent<HTMLButtonElement>) => void | Promise<unknown>;
};

export const MainButtonM = forwardRef<HTMLButtonElement, MainButtonMProps>(
  (
    {
      onClick,
      className,
      fill = 'solid',
      shape = 'rounded',
      color = 'primary',
      ...rest
    },
    ref,
  ) => {
    const [loading, setLoading] = useState(false);

    // Prevent duplicate submissions
    const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
      if (loading) {
        return;
      }
      const result = onClick?.(event);
      if (!result || !(result instanceof Promise)) {
        return;
      }

      setLoading(true);
      result
        .then(() => {
          setLoading(false);
        })
        .catch(() => {
          setLoading(false);
        });
    };

    const dataAttrs = {
      'data-fill': fill,
      'data-shape': shape,
    };

    return (
      <Button
        ref={ref}
        color={color}
        {...rest}
        {...dataAttrs}
        onClick={handleClick}
        className={classNames(styles.mainButtonM, className)}
      />
    );
  },
);

MainButtonM.displayName = 'MainButtonM';

export default memo(MainButtonM);
