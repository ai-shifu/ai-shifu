import styles from './BirthdaySettingModal.module.scss';

import { useState, memo, useCallback, useEffect, useMemo } from 'react';
import SettingBaseModal from './SettingBaseModal';

import { Calendar } from '@/components/ui/Calendar';
import { useTranslation } from 'react-i18next';

export const BirthdaySettingModal = ({
  open,
  onClose,
  onOk,
  currentBirthday,
}) => {
  const { t, i18n } = useTranslation();

  // BUGFIX: Improve state management for the birthday selector
  // Issue: After initialization the Calendar does not update when the parent changes currentBirthday
  // Fix: Use useEffect to watch currentBirthday and keep the state in sync
  // Default: Existing users see the backend value; new users default to 2000-01-01
  const [value, setValue] = useState(currentBirthday || new Date('2000-01-01'));

  useEffect(() => {
    if (currentBirthday) {
      setValue(currentBirthday);
    } else {
      setValue(new Date('2000-01-01'));
    }
  }, [currentBirthday]);

  const onOkClick = () => {
    onOk({ birthday: value });
  };

  const onChange = useCallback((val: Date | undefined) => {
    if (val) {
      setValue(val);
    }
  }, []);

  const formatters = useMemo(() => {
    const isZh = i18n.language.startsWith('zh');
    const locale = isZh ? 'zh-CN' : 'en-US';

    return {
      formatMonthCaption: (date: Date) => {
        return date.toLocaleDateString(locale, {
          year: 'numeric',
          month: 'long',
        });
      },
      formatWeekdayName: (date: Date) => {
        if (isZh) {
          const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
          return weekdays[date.getDay()];
        }
        return date.toLocaleDateString(locale, { weekday: 'short' });
      },
    };
  }, [i18n.language]);

  return (
    <SettingBaseModal
      // @ts-expect-error EXPECT
      className={styles.BirthdaySettingModal}
      open={open}
      onClose={onClose}
      onOk={onOkClick}
      closeOnMaskClick={true}
      title={t('module.settings.dialogTitle.selectBirthday')}
    >
      <Calendar
        mode='single'
        selected={value}
        onSelect={onChange}
        defaultMonth={value}
        className='rounded-lg w-full'
        formatters={formatters}
        key={i18n.language}
      />
    </SettingBaseModal>
  );
};

export default memo(BirthdaySettingModal);
