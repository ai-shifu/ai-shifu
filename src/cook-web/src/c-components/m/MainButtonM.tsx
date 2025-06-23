import styles from './MainButtonM.module.scss';

import { memo, forwardRef, useState } from 'react';
import { Button } from '@/components/ui/button';

import clsx from 'clsx';

export const MainButtonM = forwardRef((props, ref) => {
  const [loading, setLoading] = useState(false);

  // 防止重复提交
  const _onClick = (e) => {
    if (loading) {
      return
    }

    const ret = props.onClick?.(e);
    if (!(ret instanceof Promise)) {
      return
    }

    setLoading(true);
    ret.then(() => {
      setLoading(false);
    }).catch(() => {
      setLoading(false);
    });
  }

  return (
    <Button
      ref={ref}
      color="primary"
      fill="solid"
      shape='rounded'
      {...props}
      onClick={_onClick}
      className={clsx(styles.mainButtonM, props.className)}
    />
  );
});

MainButtonM.displayName = 'MainButtonM';

export default memo(MainButtonM);
