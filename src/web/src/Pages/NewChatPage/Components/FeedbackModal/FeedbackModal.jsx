import { Modal, Form, Input } from 'antd';
import MainButton from 'Components/MainButton.jsx';
import { calModalWidth } from 'Utils/common.js';
import styles from './FeedbackModal.module.scss';
import { memo } from 'react';

const FEEDBACK_MAX_LENGTH = 300;

export const FeedbackModal = ({ open, onClose, inMobile = false }) => {
  const { TextArea } = Input;

  const onSubmitFeedback = () => {};

  return (
    <Modal
      className={styles.feedbackModal}
      width={calModalWidth({ inMobile })}
      open={open}
      footer={null}
      maskClosable={true}
      onCancel={onClose}
    >
      <div className={styles.title}>反馈</div>
      <Form className={styles.formWrapper}>
        <Form.Item name="feedback">
          <TextArea
            name="feedback"
            showCount
            maxLength={FEEDBACK_MAX_LENGTH}
            style={{ height: '90px', resize: 'none' }}
          />
        </Form.Item>
      </Form>
      <MainButton className={styles.okBtn} width="100%">
        提交
      </MainButton>
    </Modal>
  );
};

export default memo(FeedbackModal);
