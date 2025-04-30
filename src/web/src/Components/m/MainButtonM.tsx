import { Button } from 'antd-mobile';
import { memo, forwardRef } from 'react';
import classNames from 'classnames';
import styles from './MainButtonM.module.scss';
import { useState } from 'react';

export const MainButtonM = forwardRef((props, ref) => {
  const [loading, setLoading] = useState(false);

  // 防止重复提交
  const _onClick = (e) => {
    if (loading) {
      return;
    }

    const ret = props.onClick?.(e);
    if (!(ret instanceof Promise)) {
      return;
    }

    setLoading(true);
    ret
      .then(() => {
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  };

  return (
    <Button
      ref={ref}
      color="primary"
      fill="solid"
      shape="rounded"
      {...props}
      onClick={_onClick}
      className={classNames(styles.mainButtonM, props.className)}
    />
  );
});

export default memo(MainButtonM);
