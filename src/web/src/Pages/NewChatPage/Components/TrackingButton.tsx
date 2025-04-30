import { Button } from 'antd';
import { tracking } from 'common/tools/tracking';

export const TrackingButton = () => {
  return (
    <Button
      onClick={() => {
        tracking('viste', { test: 'testttttt' });
      }}
    >
      测试 Tracking
    </Button>
  );
};
