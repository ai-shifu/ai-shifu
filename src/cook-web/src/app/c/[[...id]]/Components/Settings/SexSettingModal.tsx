import styles from './SexSettingModal.module.scss';

import { useCallback, memo, useState } from 'react';
import SettingBaseModal from './SettingBaseModal';

import clsx from 'clsx';
import { SEX, SEX_NAMES } from '@/c-constants/userConstants';

import { toast } from '@/hooks/use-toast';
import { useTranslation } from 'react-i18next';

import Image from 'next/image';
import iconMaleHl2x from '@/c-assets/newchat/light/icon16-male-hl@2x.png'
import iconMale2x from '@/c-assets/newchat/light/icon16-male@2x.png'
import iconFemaleHl2x from '@/c-assets/newchat/light/icon16-female-hl@2x.png'
import iconFemale2x from '@/c-assets/newchat/light/icon16-female@2x.png'
import iconAccountHl2x from '@/c-assets/newchat/light/icon16-account-hl@2x.png'
import iconAccount from '@/c-assets/newchat/light/icon16-account.png'

export const SexSettingModal = ({
  open,
  onClose,
  onOk = () => {},
  initialValues = {},
}) => {
  // @ts-expect-error EXPECT
  const [selectedSex, setSelectedSex] = useState(initialValues.sex);

  const { t } = useTranslation('tanslation', {keyPrefix: 'c'});
  const checkSelected = useCallback((sex) => {
    return sex === selectedSex;
  }, [selectedSex]);
  const getSelectedClassName = (sex) => {
    return checkSelected(sex) ? 'selected' : '';
  };

  const onOkClick = () => {
    if (!selectedSex) {
      toast({
        title: '请选择性别',
        variant: 'destructive'
      })
      return;
    }
    // @ts-expect-error EXPECT
    onOk?.({ sex: selectedSex });
  };

  const sexMaleIcon = useCallback(
    (sex) => {
      return checkSelected(sex)
        ? iconMaleHl2x.src
        : iconMale2x.src
    },
    [checkSelected]
  );

  const sexFemaleIcon = useCallback(
    (sex) => {
      return checkSelected(sex)
        ? iconFemaleHl2x.src
        : iconFemale2x.src
    },
    [checkSelected]
  );

  const sexSecretIcon = useCallback((sex) => {
    return checkSelected(sex)
      ? iconAccountHl2x.src
      : iconAccount.src
  }, [checkSelected]);

  return (
    <SettingBaseModal
      // @ts-expect-error EXPECT
      className={styles.SexSettingModal}
      open={open}
      onClose={onClose}
      onOk={onOkClick}
      title={t('settings.dialogTitle.selectSex')}
    >
      <div className={styles.sexWrapper}>
        <div
          className={clsx(styles.sexItem, getSelectedClassName(t('user.sex.male')))}
          onClick={() => setSelectedSex(t('user.sex.male'))}
        >
          <Image
            className={styles.itemIcon}
            src={sexMaleIcon(SEX_NAMES[SEX.MALE])}
            alt="male"
          />
          <div className={styles.itemTitle}>{t('user.sex.male')}</div>
        </div>
        <div
          className={clsx(
            styles.sexItem,
            getSelectedClassName(t('user.sex.female'))
          )}
          onClick={() => setSelectedSex(t('user.sex.female'))}
        >
          <Image
            className={styles.itemIcon}
            src={sexFemaleIcon(SEX_NAMES[SEX.FEMALE])}
            alt="female"
          />
          <div className={styles.itemTitle}>{t('user.sex.female')}</div>
        </div>
        <div
          className={clsx(
            styles.sexItem,
            getSelectedClassName(t('user.sex.secret'))
          )}
          onClick={() => setSelectedSex(t('user.sex.secret'))}
        >
          <Image
            className={styles.itemIcon}
            src={sexSecretIcon(t('user.sex.secret'))}
            alt="secret"
          />
          <div className={styles.itemTitle}>{t('user.sex.secret')}</div>
        </div>
      </div>
    </SettingBaseModal>
  );
};

export default memo(SexSettingModal);
