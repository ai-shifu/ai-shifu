/**
 * User settings interface
 */
import styles from './UserSettings.module.scss';

import { useState, useCallback, memo, useEffect } from 'react';

import { Button } from '@/components/ui/Button';
import SettingHeader from './SettingHeader';
import clsx from 'clsx';
import ChangeAvatar from './ChangeAvatar';
import SexSettingModal from './SexSettingModal';
import { SettingInputElement } from './SettingInputElement';
import SettingSelectElement from './SettingSelectElement';
import { updateUserProfile } from '@/c-api/user';
import BirthdaySettingModal from './BirthdaySettingModal';
import { SEX, SEX_NAMES } from '@/c-constants/userConstants';
import DynamicSettingItem from './DynamicSettingItem';
import { useUserStore } from '@/store';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import { useEnvStore } from '@/c-store/envStore';
import { getUserProfile } from '@/c-api/user';
import api from '@/api';

const fixed_keys = ['sys_user_nickname', 'avatar', 'sex', 'birth'];
const hidden_keys = ['language'];

export const UserSettings = ({
  onHomeClick,
  className,
  onClose,
  isBasicInfo = false,
}) => {
  const courseId = useEnvStore(state => state.courseId);
  const { refreshUserInfo } = useUserStore(
    useShallow(state => ({
      refreshUserInfo: state.refreshUserInfo,
    })),
  );

  const { t, i18n } = useTranslation();

  const [sexSettingModalOpen, setSexSettingModalOpen] = useState(false);
  const [birthModalOpen, setBirthModalOpen] = useState(false);

  // Avatar
  const [avatar, setAvatar] = useState('');
  // Nickname
  const [nickName, setNickName] = useState('');
  // Gender
  const [sex, setSex] = useState(SEX_NAMES[SEX.SECRET]);
  // Birthday
  const [birth, setBirth] = useState('');

  const [dynFormData, setDynFormData] = useState([]);

  const onSaveSettingsClick = useCallback(async () => {
    const data = [];
    // @ts-expect-error EXPECT
    data.push({
      key: 'sys_user_nickname',
      value: nickName,
    });
    // @ts-expect-error EXPECT
    data.push({
      key: 'avatar',
      value: avatar,
    });
    // @ts-expect-error EXPECT
    data.push({
      key: 'sex',
      value: sex,
    });
    // @ts-expect-error EXPECT
    data.push({
      key: 'birth',
      value: birth,
    });
    dynFormData.forEach(v => {
      // @ts-expect-error EXPECT
      data.push({
        // @ts-expect-error EXPECT
        key: v.key,
        // @ts-expect-error EXPECT
        value: v.value,
      });
    });
    await updateUserProfile(data, courseId);
    await refreshUserInfo();
    onClose();
  }, [
    avatar,
    birth,
    dynFormData,
    nickName,
    onClose,
    refreshUserInfo,
    sex,
    courseId,
  ]);

  const onNickNameChanged = useCallback(
    e => {
      setNickName(e.target.value);
    },
    [setNickName],
  );

  const onSexSettingModalOk = useCallback(
    e => {
      setSex(e.sex);
      setSexSettingModalOpen(false);
    },
    [setSex],
  );

  const onSexSelectClick = useCallback(() => {
    setSexSettingModalOpen(true);
  }, []);

  const onBirthClick = useCallback(() => {
    setBirthModalOpen(true);
  }, []);

  const onBirthdaySettingModalOk = useCallback(({ birthday }) => {
    const v = `${birthday.getFullYear()}-${
      birthday.getMonth() + 1
    }-${birthday.getDate()}`;
    setBirth(v);
    setBirthModalOpen(false);
  }, []);

  const onBirthdaySettingModalClose = useCallback(() => {
    setBirthModalOpen(false);
  }, []);

  const loadData = useCallback(async () => {
    if (!courseId) return;
    const respData = await getUserProfile(courseId);

    respData.forEach(v => {
      if (v.key === 'sys_user_nickname') {
        setNickName(v.value);
      } else if (v.key === 'avatar') {
        setAvatar(v.value);
      } else if (v.key === 'sex') {
        setSex(v.value);
      } else if (v.key === 'birth') {
        setBirth(v.value);
      }
    });
    setDynFormData(
      respData.filter(
        v => !fixed_keys.includes(v.key) && !hidden_keys.includes(v.key),
      ),
    );
  }, [courseId]);

  useEffect(() => {
    loadData();
  }, [i18n.language, loadData]);

  const onChangeAvatarChanged = useCallback(({ dataUrl }) => {
    setAvatar(dataUrl);
  }, []);

  const onDynamicSettingItemChange = useCallback((key, value) => {
    setDynFormData(prev => {
      return prev.map(v => {
        // @ts-expect-error EXPECT
        if (v.key === key) {
          // @ts-expect-error EXPECT
          v.value = value;
        }

        return v;
      });
    });
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  return (
    <>
      <div className={clsx(styles.UserSettings, className)}>
        <SettingHeader
          onHomeClick={onHomeClick}
          className={styles.settingHeader}
        />
        <div className={styles.settingBody}>
          <div className={styles.centerWrapper}>
            <div
              className={
                isBasicInfo
                  ? styles.basicInfoWrapper
                  : styles.basicInfoWrapperHidden
              }
            >
              {/* @ts-expect-error EXPECT */}
              <ChangeAvatar
                image={avatar}
                onChange={onChangeAvatarChanged}
              />
              <div className={styles.basicInfoTitle}>
                {t('module.settings.basicInfo')}
              </div>
              <SettingInputElement
                title={t('module.settings.nickname')}
                placeholder={t('module.settings.nicknamePlaceholder')}
                onChange={onNickNameChanged}
                className={styles.inputUnit}
                value={nickName}
                // @ts-expect-error EXPECT
                maxLength={10}
              />
              <SettingSelectElement
                title={t('module.settings.gender')}
                placeholder={t('module.settings.genderPlaceholder')}
                value={sex}
                className={styles.inputUnit}
                onClick={onSexSelectClick}
              />
              <SettingSelectElement
                title={t('module.settings.birth')}
                placeholder={t('module.settings.birthPlaceholder')}
                className={styles.inputUnit}
                onClick={onBirthClick}
                value={birth}
              />
            </div>

            <div
              className={
                isBasicInfo
                  ? styles.basicInfoWrapperHidden
                  : styles.basicInfoWrapper
              }
            >
              <div className={clsx(styles.basicInfoTitle)}>
                {t('module.settings.personalInfo')}
              </div>
              <SettingInputElement
                title={t('module.settings.nicknamePersonal')}
                placeholder={t('module.settings.nicknamePlaceholder')}
                onChange={onNickNameChanged}
                className={styles.inputUnit}
                value={nickName}
                // @ts-expect-error EXPECT
                maxLength={10}
              />
              {dynFormData.map(item => {
                return (
                  <DynamicSettingItem
                    // @ts-expect-error EXPECT
                    key={item.key}
                    settingItem={item}
                    onChange={onDynamicSettingItemChange}
                    className={styles.inputUnit}
                  />
                );
              })}
            </div>
          </div>
        </div>
        <div className={styles.settingFooter}>
          <div className={styles.centerWrapper}>
            <Button
              className={styles.saveBtn}
              onClick={onSaveSettingsClick}
            >
              保存
            </Button>
          </div>
        </div>
      </div>
      <BirthdaySettingModal
        open={birthModalOpen}
        onOk={onBirthdaySettingModalOk}
        onClose={onBirthdaySettingModalClose}
        currentBirthday={birth ? new Date(birth) : undefined}
      />
      <SexSettingModal
        open={sexSettingModalOpen}
        // @ts-expect-error EXPECT
        onOk={onSexSettingModalOk}
        onClose={() => setSexSettingModalOpen(false)}
        initialValues={{ sex }}
      />
    </>
  );
};

export default memo(UserSettings);
