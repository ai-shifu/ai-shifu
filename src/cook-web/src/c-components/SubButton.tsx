import styles from "./SubButton.module.scss";

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

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
      disabled={disabled}
      className={cn('round-full', styles.mainButton)}
      style={{ width, height, ...style }}
      onClick={onClick}
    >
      {children}
    </Button>
  );
};

export default SubButton;
