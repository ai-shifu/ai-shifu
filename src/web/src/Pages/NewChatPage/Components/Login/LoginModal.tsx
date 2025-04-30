import classNames from 'classnames';
import { useState } from 'react';
import { Modal, Input, Button, Checkbox, Form, message } from 'antd';
import { useSendCode } from './useSendCode';
import styles from './LoginModal.module.scss';
import MainButton from 'Components/MainButton';
import { calModalWidth } from 'Utils/common';
import { genCheckCode } from 'Api/user';
import { useUserStore } from 'stores/useUserStore';
import { useTranslation } from 'react-i18next';
import { memo } from 'react';
import { useCallback } from 'react';
import { useRef } from 'react';

const MODAL_STEP = {
  MOBILE: 1,
  CODE: 2,
  VERIFY_CODE: 3,
};

export const LoginModal = ({
  open,
  width,
  onClose = () => {},
  inMobile = false,
  onFeedbackClick,
  onLogin = () => {},
}) => {
  const [mobile, setMobile] = useState('');
  const [mobileForm] = Form.useForm();
  const [codeForm] = Form.useForm();
  const [verifyCodeForm] = Form.useForm();
  const [modalStep, setModalStep] = useState(MODAL_STEP.MOBILE);
  const [countDown, sendCode] = useSendCode({});
  const [agreement, setAgreement] = useState(false);
  const [verifyCodeImage, setVerifyCodeImage] = useState('');
  const [messageApi, contextHolder] = message.useMessage();
  const login = useUserStore((state) => state.login);
  const { t } = useTranslation();

  const mobileInputRef = useRef(null);
  const smsCodeInputRef = useRef(null);
  const verifyCodeInputRef = useRef(null);

  const updateVerifyCodeImage = async (mobile) => {
    const { data: res } = await genCheckCode(mobile);
    setVerifyCodeImage(res.img);
  };
  const clearVerifyCode = () => {
    verifyCodeForm.resetFields();
  };

  const onMobileFormOkClick = async () => {
    try {
      const { mobile } = await mobileForm.validateFields();
      setMobile(mobile);
      updateVerifyCodeImage(mobile);
      setModalStep(MODAL_STEP.VERIFY_CODE);
    } catch {}
  };

  const onResendClick = async () => {
    try {
      updateVerifyCodeImage(mobile);
      setModalStep(MODAL_STEP.VERIFY_CODE);
      clearVerifyCode();
    } catch {}
  };

  const onVerifyCodeFormOkClick = async () => {
    try {
      const { checkCode } = await verifyCodeForm.validateFields();
      try {
        await sendCode(mobile, checkCode);
        setModalStep(MODAL_STEP.CODE);
      } catch (ex) {
        messageApi.error(ex.message);
      }
    } catch {}
  };

  const onCodeFormkOkClick = async () => {
    try {
      const { smsCode } = await codeForm.validateFields();

      if (!agreement) {
        messageApi.error(t('user.msgToAgree'));
        return;
      }

      await login({ mobile, smsCode });
      messageApi.success(t('user.msgLoginSuccess'));
      onLogin?.();
      onClose?.();
    } catch {}
  };

  const onLoginClick = async () => {
    if (modalStep === MODAL_STEP.MOBILE) {
      await onMobileFormOkClick();
    }

    if (modalStep === MODAL_STEP.CODE) {
      await onCodeFormkOkClick();
    }

    if (modalStep === MODAL_STEP.VERIFY_CODE) {
      await onVerifyCodeFormOkClick();
    }
  };

  const onFeedbackButtonClick = useCallback(
    (e) => {
      e.preventDefault();
      onFeedbackClick?.();
      onClose();
    },
    [onClose, onFeedbackClick],
  );

  const onAfterOpenChange = useCallback(() => {
    if (modalStep === MODAL_STEP.MOBILE) {
      mobileInputRef.current?.focus();
    } else if (modalStep === MODAL_STEP.CODE) {
      smsCodeInputRef.current?.focus();
    } else if (modalStep === MODAL_STEP.VERIFY_CODE) {
      verifyCodeInputRef.current?.focus();
    }
  }, [modalStep]);

  return (
    <Modal
      open={open}
      footer={null}
      className={styles.loginModal}
      width={calModalWidth({ inMobile, width })}
      onCancel={onClose}
      afterOpenChange={onAfterOpenChange}
    >
      <div className={styles.title}>{t('user.loginTitle')}</div>
      <div className={styles.formWrapper}>
        {modalStep === MODAL_STEP.MOBILE && (
          <Form form={mobileForm} className={styles.mobileForm}>
            <Form.Item
              name="mobile"
              rules={[
                {
                  required: true,
                  message: t('user.msgToInputPhone'),
                  pattern: /^1\d{10}$/,
                },
              ]}
            >
              <Input
                ref={mobileInputRef}
                className={classNames(styles.mobile, styles.sfInput)}
                placeholder={t('user.msgToInputPhone')}
                maxLength={11}
                onPressEnter={(e) => {
                  e.stopPropagation();
                  onMobileFormOkClick();
                }}
              />
            </Form.Item>
          </Form>
        )}
        {modalStep === MODAL_STEP.CODE && (
          <Form form={codeForm} className={styles.codeForm}>
            <Form.Item
              name="smsCode"
              rules={[
                {
                  required: true,
                  message: t('user.msgToInputCode'),
                  pattern: /^\d{4}$/,
                },
              ]}
            >
              <Input
                ref={smsCodeInputRef}
                className={classNames(styles.smsCode, styles.sfInput)}
                maxLength={4}
                placeholder={t('user.msgToInputCode')}
                onPressEnter={(e) => {
                  e.stopPropagation();
                  onCodeFormkOkClick();
                }}
              />
            </Form.Item>
            <Button
              className={styles.sendBtn}
              disabled={countDown > 0}
              type="link"
              onClick={onResendClick}
            >
              {countDown > 0
                ? t('user.msgResendCode') + `(${countDown})`
                : t('user.msgResendCode')}
            </Button>
          </Form>
        )}
        {modalStep === MODAL_STEP.VERIFY_CODE && (
          <Form className={styles.verifyCodeForm} form={verifyCodeForm}>
            <Form.Item
              name="checkCode"
              rules={[
                {
                  required: true,
                  message: t('user.msgToInputCode4'),
                  pattern: /^[a-zA-Z0-9]{0,4}$/,
                },
              ]}
            >
              <Input
                ref={verifyCodeInputRef}
                className={classNames(styles.verifyCode, styles.sfInput)}
                maxLength={4}
                placeholder={t('user.msgToInputCode4')}
                onPressEnter={(e) => {
                  e.stopPropagation();
                  onVerifyCodeFormOkClick();
                }}
              />
            </Form.Item>
            <img
              className={styles.vcodeImage}
              src={verifyCodeImage}
              alt={t('user.msgCheckCode')}
              onClick={() => {
                updateVerifyCodeImage(mobile);
              }}
            />
          </Form>
        )}
        <div
          className={styles.verifyCodeWrapper}
          style={{ display: 'none' }}
        ></div>
      </div>
      <div className={styles.agreementWrapper}>
        <div className={styles.agreement}>
          <Checkbox
            className={styles.checkbox}
            onChange={(e) => setAgreement(e.target.checked)}
          >
            {t('user.msgHaveRead')}
            <span className={styles.link}>
              <a href="/useragreement" target="_blank" rel="noreferrer">
                {t('user.msgAgreement')}
              </a>
              {t('user.msgAnd')}
              <a
                className={styles.link}
                href="/privacypolicy"
                target="_blank"
                rel="noreferrer"
              >
                {t('user.msgPrivacyPolicy')}
              </a>
            </span>
          </Checkbox>
        </div>
        <div className={styles.feedback}>
          {t('user.msgLoginProblem')}
          <a
            href="x"
            className={styles.link}
            target="_blank"
            rel="noreferrer"
            onClick={onFeedbackButtonClick}
          >
            {t('user.loginFeedback')}
          </a>
        </div>
      </div>
      <div className={styles.btnWrapper}>
        <MainButton onClick={onLoginClick} width="100%">
          {t('user.loginMainButton')}
        </MainButton>
      </div>
      {contextHolder}
    </Modal>
  );
};

export default memo(LoginModal);
