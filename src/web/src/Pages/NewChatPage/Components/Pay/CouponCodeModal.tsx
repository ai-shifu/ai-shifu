import { Modal, Form, Input } from 'antd';
import { useCallback } from 'react';
import { memo } from 'react';
import styles from './CouponCodeModal.module.scss';
import { useTranslation } from 'react-i18next';

export const CouponCodeModal = ({ open = false, onCancel, onOk }) => {
  const [form] = Form.useForm();
  const { t } = useTranslation();

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
      title={t('groupon.grouponTitle')}
      width="400px"
      onOk={_onOk}
      className={styles.couponCodeModal}
      maskClosable={false}
    >
      <Form form={form}>
        <Form.Item
          rules={[{ required: true, message: t('groupon.grouponInputMsg') }]}
          name="couponCode"
        >
          <Input
            placeholder={t('groupon.grouponPlaceholder')}
            name="couponCode"
          />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default memo(CouponCodeModal);
