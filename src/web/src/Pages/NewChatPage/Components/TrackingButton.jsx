import { Button } from "antd";
import { tracking } from "common/tools/tracking.js";

export const TrackingButton = () => {
  return <Button onClick={() => {
    tracking('viste', { test: 'testttttt'})
  }}>测试 Tracking</Button>
}
