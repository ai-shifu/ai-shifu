import { useState } from 'react';
import styles from './BirthdaySettingModal.module.scss';
import SettingBaseModal from './SettingBaseModal.jsx';
import { DatePickerView, Modal } from 'antd-mobile';
import { useEffect } from 'react';

export const BirthdaySettingModal = ({
  open,
  onClose,
  onOk = ({ birthday }) => {},
  initialValues = {},
}) => {
  const [value, setValue] = useState(new Date());
  const [showPicker, setShowPicker] = useState(true);
  const onOkClick = () => {};
  const now = new Date();


  return (
    <SettingBaseModal
      className={styles.SexSettingModal}
      open={open}
      onClose={onClose}
      onOk={onOkClick}
      loading={!showPicker}
      closeOnMaskClick={true}
    >
      <DatePickerView
        defaultValue={now}
        onChange={(val) => {
          setValue(val);
        }}
      />
    </SettingBaseModal>
  );
};

export default BirthdaySettingModal;
