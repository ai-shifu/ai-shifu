import SettingBaseModal from "./SettingBaseModal.jsx";
import { Form, Input } from "antd";
import styles from "./IndustrySettingModal.module.scss";

export const IndustrySettingModal = ({
  open,
  onClose,
  onOk = ({ industry }) => {},
  initialValues = {},
}) => {
  const [form] = Form.useForm();

  const onOkClick = async () => {
    try {
      const { industry } = await form.validateFields();
      onOk?.({ industry });
    } catch (ex) {}
  };

  return (
    <SettingBaseModal
      open={open}
      onClose={onClose}
      onOk={onOkClick}
      title='行业'
    >
      <Form
        form={form}
        initialValues={initialValues}>
        <Form.Item
          name="industry"
          rules={[
            { required: true, message: "请输入行业" },
            { type: "string", max: 20, message: "长度不能超过20" },
          ]}
        >
          <Input
            placeholder="请输入行业"
            className={styles.sfInput}
          />
        </Form.Item>
      </Form>
    </SettingBaseModal>
  );
};

export default IndustrySettingModal;
