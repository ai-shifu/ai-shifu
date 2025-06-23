import styles from './MainButton.module.scss';
import { cn } from '@/lib/utils'

import { Button } from '@/components/ui/button';
// import { Button } from 'antd';
// import { ConfigProvider } from 'antd';
import { forwardRef, memo } from 'react';

export const LineButton = forwardRef((props, ref) => {
  // TODO: FIXME
  return (
    <Button
        ref={ref}
        {...props}
        className={cn('size-max', 'px-1')}
      >
      {props.children}
    </Button>
    // <ConfigProvider
    //   theme={{
    //     components: {
    //       Button: {
    //         defaultColor: '#042ED2',
    //         defaultHoverColor: '#3658DB',
    //         defaultActiveColor: '#0325A8',
    //         defaultBorderColor: '#042ED2',
    //         defaultHoverBorderColor: '#3658DB',
    //         defaultActiveBorderColor: '#0325A8',
    //       },
    //     },
    //   }}
    // >
    //   <Button
    //     ref={ref}
    //     {...props}
    //     type="default"
    //     className={classNames(styles.mainButton, props.className)}
    //     style={{ width: props.width, height: props.height, ...props.style }}
    //   >
    //     {props.children}
    //   </Button>
    // </ConfigProvider>
  );
});

LineButton.displayName = 'LineButton';

export default memo(LineButton);
