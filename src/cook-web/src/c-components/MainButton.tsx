import styles from './MainButton.module.scss';
import clsx from 'clsx';

import { Button } from '@/components/ui/button';

// import { Button } from 'antd';
// import { ConfigProvider } from 'antd';

import { forwardRef, memo } from 'react';

export const MainButton = forwardRef((props, ref) => {
  const height = props.height || 40;

  return (
    <Button
      ref={ref}
      {...props}
      className={clsx('rounded-full', styles.mainButton, props.className)}
      style={{ width: props.width, height, ...props.style }}
    >
      {props.children}
    </Button>

    // <ConfigProvider
    //   theme={{
    //     components: {
    //       Button: {
    //         colorPrimary: '#042ED2',
    //         colorPrimaryHover: '#3658DB',
    //         colorPrimaryActive: '#0325A8',
    //         lineWidth: 0,
    //       },
    //     },
    //   }}
    // >
    //   <Button
    //     ref={ref}
    //     {...props}
    //     type="primary"
    //     shape="round"
    //     className={classNames(styles.mainButton, props.className)}
    //     style={{ width: props.width, height, ...props.style }}
    //   >
    //     {props.children}
    //   </Button>
    // </ConfigProvider>
  );
});

export default memo(MainButton);
