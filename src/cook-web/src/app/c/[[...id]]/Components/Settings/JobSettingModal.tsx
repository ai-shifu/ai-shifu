import { memo } from 'react';
import styles from './JobSettingModal.module.scss';
import SettingBaseModal from './SettingBaseModal';
import { Form, Input } from 'antd';

export const JobSettingModal = ({
  open,
  onClose,
  onOk = ({ job }) => {},
  initialValues = {},
}) => {
  const [form] = Form.useForm();
  const onOkClick = async () => {
    try {
      const { job } = await form.validateFields();
      onOk?.({ job });
    } catch (ex) {}
  };

  return (
    <SettingBaseModal
      open={open}
      onClose={onClose}
      onOk={onOkClick}
      title="职业"
    >
      <Form form={form} initialValues={initialValues}>
        <Form.Item
          name="job"
          rules={[
            { required: true, message: '请输入职业' },
            { type: 'string', max: 20, message: '长度不能超过20' },
          ]}
        >
          <Input placeholder="请输入职业" className={styles.sfInput} />
        </Form.Item>
      </Form>
    </SettingBaseModal>
  );
};

export default memo(JobSettingModal);
