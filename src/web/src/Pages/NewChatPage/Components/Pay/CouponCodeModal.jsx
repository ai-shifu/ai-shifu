import { Modal, Form, Input } from 'antd';
import { useCallback } from 'react';
import { memo } from 'react';
import styles from './CouponCodeModal.module.scss';

export const CouponCodeModal = ({ open = false, onCancel, onOk }) => {
  const [form] = Form.useForm();

  const _onOk = useCallback(async () => {
    try {
      const values = await form.validateFields();
      onOk?.(values);
    } catch {}
  }, [form, onOk]);
  return (
    <Modal
      open={open}
      onCancel={onCancel}
      title={'优惠码'}
      width="400px"
      onOk={_onOk}
      className={styles.couponCodeModal}
      maskClosable={false}
    >
      <Form form={form}>
        <Form.Item
          rules={[{ required: true, message: '请输入优惠码' }]}
          name="couponCode"
        >
          <Input placeholder="请输入优惠码" name="couponCode" />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default memo(CouponCodeModal);
