/**
 * 用户配置界面
 */
import styles from './UserSettings.module.scss';
import MainButton from 'Components/MainButton';
import SettingHeader from './SettingHeader';
import classNames from 'classnames';
import ChangeAvatar from './ChangeAvatar';
import SexSettingModal from './SexSettingModal';
import { useState } from 'react';
import { useCallback } from 'react';
import { SettingInputElement } from './SettingInputElement';
import SettingSelectElement from './SettingSelectElement';
import { memo } from 'react';
import { getUserProfile, updateUserProfile } from 'Api/user';
import { useEffect } from 'react';
import BirthdaySettingModal from './BirthdaySettingModal';
import { SEX, SEX_NAMES } from 'constants/userConstants';
import DynamicSettingItem from './DynamicSettingItem';
import { useUserStore } from 'stores/useUserStore';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import { useEnvStore } from 'stores/envStore';

// These keys are included in basic information
const fixed_keys = ['sys_user_nickname', 'avatar', 'sex', 'birth'];
// These keys and the above keys are not displayed in the personalized information
const hidden_keys = ['language'];

export const UserSettings = ({
  onHomeClick,
  className,
  onClose,
  isBasicInfo = false,
}) => {
  const courseId = useEnvStore((state) => state.courseId);
  const { refreshUserInfo } = useUserStore(
    useShallow((state) => ({
      refreshUserInfo: state.refreshUserInfo,
    }))
  );

  const { t, i18n } = useTranslation();

  const [sexSettingModalOpen, setSexSettingModalOpen] = useState(false);
  const [birthModalOpen, setBirthModalOpen] = useState(false);

  // 头像
  const [avatar, setAvatar] = useState('');
  // 昵称
  const [nickName, setNickName] = useState('');
  // 性别
  const [sex, setSex] = useState(SEX_NAMES[SEX.SECRET]);
  // 生日
  const [birth, setBirth] = useState('');

  const [dynFormData, setDynFormData] = useState([]);

  const onSaveSettingsClick = useCallback(async () => {
    const data = [];
    data.push({
      key: 'sys_user_nickname',
      value: nickName,
    });
    data.push({
      key: 'avatar',
      value: avatar,
    });
    data.push({
      key: 'sex',
      value: sex,
    });
    data.push({
      key: 'birth',
      value: birth,
    });
    dynFormData.forEach((v) => {
      data.push({
        key: v.key,
        value: v.value,
      });
    });
    await updateUserProfile(data, courseId);
    await refreshUserInfo();
    onClose();
  }, [avatar, birth, dynFormData, nickName, onClose, refreshUserInfo, sex, courseId]);

  const onNickNameChanged = useCallback(
    (e) => {
      setNickName(e.target.value);
    },
    [setNickName]
  );

  const onSexSettingModalOk = useCallback(
    (e) => {
      setSex(e.sex);
      setSexSettingModalOpen(false);
    },
    [setSex]
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
    const { data: respData } = await getUserProfile(courseId);
    respData.forEach((v) => {
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
    setDynFormData(respData.filter((v) => (!fixed_keys.includes(v.key) && !hidden_keys.includes(v.key))));
  }, []);


  useEffect(() => {
    loadData();
  },[i18n.language,loadData]);

  const onChangeAvatarChanged = useCallback(({ dataUrl }) => {
    setAvatar(dataUrl);
  }, []);

  const onDynamicSettingItemChange = useCallback((key, value) => {
    setDynFormData((prev) => {
      return prev.map((v) => {
        if (v.key === key) {
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
      <div className={classNames(styles.UserSettings, className)}>
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
              <ChangeAvatar image={avatar} onChange={onChangeAvatarChanged} />
              <div className={styles.basicInfoTitle}>
                {t('settings.basicInfo')}
              </div>
              <SettingInputElement
                title={t('settings.nickname')}
                placeholder={t('settings.nicknamePlaceholder')}
                onChange={onNickNameChanged}
                className={styles.inputUnit}
                value={nickName}
                maxLength={10}
              />
              <SettingSelectElement
                title={t('settings.sex')}
                placeholder={t('settings.sexPlaceholder')}
                value={sex}
                className={styles.inputUnit}
                onClick={onSexSelectClick}
              />
              <SettingSelectElement
                title={t('settings.birth')}
                placeholder={t('settings.birthPlaceholder')}
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
              <div className={classNames(styles.basicInfoTitle)}>
                {t('settings.personalInfo')}
              </div>
              <SettingInputElement
                title={t('settings.nicknamePersonal')}
                placeholder={t('settings.nicknamePlaceholder')}
                onChange={onNickNameChanged}
                className={styles.inputUnit}
                value={nickName}
                maxLength={10}
              />
              {dynFormData.map((item) => {
                return (
                  <DynamicSettingItem
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
            <MainButton
              className={styles.saveBtn}
              onClick={onSaveSettingsClick}
            >
              保存
            </MainButton>
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
        onOk={onSexSettingModalOk}
        onClose={() => setSexSettingModalOpen(false)}
        initialValues={{ sex }}
      />
    </>
  );
};

export default memo(UserSettings);
