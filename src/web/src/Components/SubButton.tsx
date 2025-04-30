import { Button } from 'antd';
import styles from './SubButton.module.scss';

const SubButton = ({
  disabled,
  children,
  width,
  height = 40,
  style,
  onClick,
}) => {
  return (
    <Button
      shape="round"
      disabled={disabled}
      className={styles.mainButton}
      style={{ width, height, ...style }}
      onClick={onClick}
    >
      {children}
    </Button>
  );
};

export default SubButton;
