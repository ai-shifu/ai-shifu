import { Button } from 'antd';
import styles from './MainButton.module.scss';
import classNames from 'classnames';
import { ConfigProvider } from 'antd';
import { forwardRef, memo } from 'react';

export const MainButton = forwardRef((props, ref) => {
  const height = props.height || 40;
  const shape = props.shape || 'round';
  return (
    <ConfigProvider
      theme={{
        components: {
          Button: {
            colorPrimary: '#0f63ee',
            colorPrimaryHover: '#3658DB',
            colorPrimaryActive: '#0325A8',
            lineWidth: 0,
          },
        },
      }}
    >
      <Button
        ref={ref}
        {...props}
        type="primary"
        shape={shape}
        className={classNames(styles.mainButton, props.className)}
        style={{ width: props.width, height, ...props.style }}
      >
        {props.children}
      </Button>
    </ConfigProvider>
  );
});

export default memo(MainButton);
