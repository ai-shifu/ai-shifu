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

  // BUGFIX: 生日选择器状态管理优化
  // 问题：组件初始化后，当父组件传入的currentBirthday发生变化时，Calendar不会同步更新
  // 解决：使用useEffect监听currentBirthday变化，确保状态同步
  // 默认值：已有用户显示后端返回的生日，新用户默认2000-01-01
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
      title={t('settings.dialogTitle.selectBirthday')}
    >
      <Calendar
        mode='single'
        selected={value}
        onSelect={onChange}
        defaultMonth={value}
        className='rounded-lg'
        formatters={formatters}
        key={i18n.language}
      />
    </SettingBaseModal>
  );
};

export default memo(BirthdaySettingModal);
