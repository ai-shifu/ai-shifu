import { useCallback, useState, memo } from 'react';
import styles from './BirthdaySettingModal.module.scss';
import SettingBaseModal from './SettingBaseModal';

import { Calendar } from "@/components/ui/calendar"
import { useTranslation } from 'react-i18next';

export const BirthdaySettingModal = ({
  open,
  onClose,
  onOk = ({ birthday }) => {},
  currentBirthday,
}) => {
  const { t } = useTranslation('translation', {keyPrefix: 'c'});

  const [value, setValue] = useState(currentBirthday || new Date('2000-01-01'));
  const onOkClick = () => {
    onOk({ birthday: value });
  };
  const now = new Date();
  const min = new Date();
  min.setFullYear(now.getFullYear() - 100);

  const _onChange = useCallback((val) => {
    setValue(val);
  }, []);

  return (
    <SettingBaseModal
      className={styles.SexSettingModal}
      open={open}
      onClose={onClose}
      onOk={onOkClick}
      closeOnMaskClick={true}
      title={t('settings.dialogTitle.selectBirthday')}
    >
      <Calendar
        mode='single'
        className="rounded-lg"
      />
    </SettingBaseModal>
  );
};

export default memo(BirthdaySettingModal);
