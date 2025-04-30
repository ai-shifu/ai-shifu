import styles from './RadioM.module.scss';
import { memo, forwardRef } from 'react';
import classNames from 'classnames';
import { Radio } from 'antd-mobile';

export const RadioM = forwardRef((props, ref) => {
  return (
    <Radio
      ref={ref}
      {...props}
      className={classNames(styles.radioM, props.className)}
    />
  );
});

RadioM.Group = Radio.Group;

export default memo(RadioM);
