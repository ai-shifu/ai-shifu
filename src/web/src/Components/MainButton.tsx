import { Button } from 'antd';
import styles from './MainButton.module.scss';
import classNames from 'classnames';
import { ConfigProvider } from 'antd';
import { forwardRef, memo } from 'react';

export const MainButton = forwardRef((props, ref) => {
  const height = props.height || 40;
  return (
    <ConfigProvider
      theme={{
        components: {
          Button: {
            colorPrimary: '#042ED2',
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
        shape="round"
        className={classNames(styles.mainButton, props.className)}
        style={{ width: props.width, height, ...props.style }}
      >
        {props.children}
      </Button>
    </ConfigProvider>
  );
});

export default memo(MainButton);
