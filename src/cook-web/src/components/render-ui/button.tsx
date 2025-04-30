import React, { useState } from 'react';
import { Input } from '../ui/input';
import { Button as UIButton } from '../ui/button';

interface ButtonProps {
  properties: {
    button_name: string;
    button_key: string;
  };
  onChange: (properties: any) => void;
  mode?: 'edit' | 'login' | 'payment';
}

export default function Button(props: ButtonProps) {
  const { properties, mode = 'edit' } = props;
  const [tempValue, setTempValue] = useState(properties.button_name);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setTempValue(value);
    if (mode === 'login' || mode === 'payment') {
      props.onChange({
        ...properties,
        button_name: value,
        button_key: value,
      });
    }
  };

  const handleConfirm = () => {
    props.onChange({
      ...properties,
      button_name: tempValue,
      button_key: tempValue,
    });
  };

  return (
    <div className="flex flex-col space-y-2">
      <div className="flex flex-row space-x-1 items-center">
        <span className="flex flex-row whitespace-nowrap w-[70px] shrink-0">
          按钮文案：
        </span>
        <Input
          className="h-8 w-40"
          value={tempValue}
          onChange={handleInputChange}
        />
      </div>

      {mode === 'edit' && (
        <div className="flex flex-row space-x-1 items-center">
          <span className="flex flex-row whitespace-nowrap w-[70px] shrink-0"></span>
          <UIButton className="h-8 w-20" onClick={handleConfirm}>
            完成
          </UIButton>
        </div>
      )}
    </div>
  );
}
