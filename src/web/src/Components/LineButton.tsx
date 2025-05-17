import { Button } from 'antd';
import styles from './MainButton.module.scss';
import classNames from 'classnames';
import { ConfigProvider } from 'antd';
import { forwardRef, memo } from 'react';

export interface LineButtonProps extends React.ComponentProps<typeof Button> {
  width?: number | string;
  height?: number | string;
}
export const LineButton = forwardRef<HTMLButtonElement, LineButtonProps>((props, ref) => {
  return (
    <ConfigProvider
      theme={{
        components: {
          Button: {
            defaultColor: '#042ED2',
            defaultHoverColor: '#3658DB',
            defaultActiveColor: '#0325A8',
            defaultBorderColor: '#042ED2',
            defaultHoverBorderColor: '#3658DB',
            defaultActiveBorderColor: '#0325A8',
          },
        },
      }}
    >
      <Button
        ref={ref}
        {...props}
        type="default"
        className={classNames(styles.mainButton, props.className)}
        style={{ width: props.width, height: props.height, ...props.style }}
      >
        {props.children}
      </Button>
    </ConfigProvider>
  );
});

export default memo(LineButton);
