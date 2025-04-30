import { memo } from 'react';
import classNames from 'classnames';
import styles from './ToPayButton.module.scss';
import { Button, ConfigProvider } from 'antd';

const ToPayButton = ({
  children,
  className = '',
  onClick,
  height = '26px',
}) => {
  return (
    <ConfigProvider
      theme={{
        components: {
          Button: {
            colorBorder: '#d8b582',
            colorPrimaryBorderHover: '#d8b582',
            defaultColor: '#854C2B',
            defaultBg: 'linear-gradient(to top right, #FFF5E6, #F7E0BE)',
            defaultBorderColor: '#d8b582',
            defaultHoverColor: '#854C2B',
            defaultHoverBorderColor: '#d8b582',
            defaultHoverBg:
              'linear-gradient(to bottom right, #F7E0BE, #FFF5E6)',
            defaultActiveColor: '#854C2B',
            defaultActiveBorderColor: '#d8b582',
            defaultActiveBg:
              'linear-gradient(to bottom right, #F7E0BE, #FFF5E6)',
          },
        },
      }}
    >
      <Button
        className={classNames(styles.toPayButton, className)}
        style={{ height }}
        onClick={onClick}
      >
        {children}
      </Button>
    </ConfigProvider>
  );
};

export default memo(ToPayButton);
