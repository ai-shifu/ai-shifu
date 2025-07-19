import { memo } from 'react';
import SettingInputElement from './SettingInputElement';
import SettingRadioElement from './SettingRadioElement';

export const DynamicSettingItem = ({ settingItem, onChange, className }) => {
  const _onInputChange = (e) => {
    onChange(settingItem.key, e.target.value);
  };

  const _onRaidoChange = (e) => {
    onChange(settingItem.key, e);
  }

  return (
    <>
      {settingItem.type === 'text' && (
        <SettingInputElement
          title={settingItem.label}
          placeholder={settingItem.label}
          onChange={_onInputChange}
          className={className}
          value={settingItem.value}
        />
      )}
      {settingItem.type === 'select' && <SettingRadioElement
          title={settingItem.label}
          // @ts-expect-error EXPECT
          placeholder={settingItem.label}
          onChange={_onRaidoChange}
          className={className}
          value={settingItem.value}
          options={settingItem.items.map((option) => ({
            label: option,
            value: option,
          }))}
      />}
    </>
  );
};

export default memo(DynamicSettingItem);
