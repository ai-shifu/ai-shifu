import { useState } from 'react';
import styles from './SexSettingModal.module.scss';
import SettingBaseModal from './SettingBaseModal';
import classNames from 'classnames';
import { SEX, SEX_NAMES } from 'constants/userConstants';
import { message } from 'antd';
import { useCallback } from 'react';
import { memo } from 'react';
import { useTranslation } from 'react-i18next';

export const SexSettingModal = ({
  open,
  onClose,
  onOk = ({ sex }) => {},
  initialValues = {},
}) => {
  const [selectedSex, setSelectedSex] = useState(initialValues.sex);
  const [messageApi, contextHolder] = message.useMessage();
  const { t } = useTranslation();
  const checkSelected = useCallback(
    (sex) => {
      return sex === selectedSex;
    },
    [selectedSex],
  );
  const getSelectedClassName = (sex) => {
    return checkSelected(sex) ? 'selected' : '';
  };

  const onOkClick = () => {
    if (!selectedSex) {
      messageApi.error('请选择性别');
      return;
    }

    onOk?.({ sex: selectedSex });
  };

  const sexMaleIcon = useCallback(
    (sex) => {
      return checkSelected(sex)
        ? require('@Assets/newchat/light/icon16-male-hl@2x.png')
        : require('@Assets/newchat/light/icon16-male@2x.png');
    },
    [checkSelected],
  );

  const sexFemaleIcon = useCallback(
    (sex) => {
      return checkSelected(sex)
        ? require('@Assets/newchat/light/icon16-female-hl@2x.png')
        : require('@Assets/newchat/light/icon16-female@2x.png');
    },
    [checkSelected],
  );

  const sexSecretIcon = useCallback(
    (sex) => {
      return checkSelected(sex)
        ? require('@Assets/newchat/light/icon16-account-hl@2x.png')
        : require('@Assets/newchat/light/icon16-account.png');
    },
    [checkSelected],
  );

  return (
    <SettingBaseModal
      className={styles.SexSettingModal}
      open={open}
      onClose={onClose}
      onOk={onOkClick}
      title={t('settings.dialogTitle.selectSex')}
    >
      <div className={styles.sexWrapper}>
        <div
          className={classNames(
            styles.sexItem,
            getSelectedClassName(t('user.sex.male')),
          )}
          onClick={() => setSelectedSex(t('user.sex.male'))}
        >
          <img
            className={styles.itemIcon}
            src={sexMaleIcon(SEX_NAMES[SEX.MALE])}
            alt="male"
          />
          <div className={styles.itemTitle}>{t('user.sex.male')}</div>
        </div>
        <div
          className={classNames(
            styles.sexItem,
            getSelectedClassName(t('user.sex.female')),
          )}
          onClick={() => setSelectedSex(t('user.sex.female'))}
        >
          <img
            className={styles.itemIcon}
            src={sexFemaleIcon(SEX_NAMES[SEX.FEMALE])}
            alt="female"
          />
          <div className={styles.itemTitle}>{t('user.sex.female')}</div>
        </div>
        <div
          className={classNames(
            styles.sexItem,
            getSelectedClassName(t('user.sex.secret')),
          )}
          onClick={() => setSelectedSex(t('user.sex.secret'))}
        >
          <img
            className={styles.itemIcon}
            src={sexSecretIcon(t('user.sex.secret'))}
            alt="secret"
          />
          <div className={styles.itemTitle}>{t('user.sex.secret')}</div>
        </div>
      </div>
      {contextHolder}
    </SettingBaseModal>
  );
};

export default memo(SexSettingModal);
