import React, { useState } from 'react';
import { Input } from '../ui/input';
import { Textarea } from '../ui/textarea';
import InputNumber from '@/components/input-number';
import ModelList from '@/components/model-list';
import { Button } from '../ui/button';

interface ButtonProps {
  properties: {
    prompt: {
      properties: {
        prompt: string;
        profiles: string[];
        model: string;
        temprature: string;
        other_conf: string;
      };
      type: string;
    };
    input_name: string;
    input_key: string;
    input_placeholder: string;
  };
  onChange: (properties: any) => void;
}

export default function TextInput(props: ButtonProps) {
  const { properties } = props;
  const [tempProperties, setTempProperties] = useState(properties);

  const onValueChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setTempProperties({
      ...tempProperties,
      prompt: {
        ...tempProperties.prompt,
        properties: {
          ...tempProperties.prompt.properties,
          prompt: e.target.value,
        },
      },
    });
  };

  const onModelChange = (value: string) => {
    setTempProperties({
      ...tempProperties,
      prompt: {
        ...tempProperties.prompt,
        properties: {
          ...tempProperties.prompt.properties,
          model: value,
        },
      },
    });
  };

  const onTemperatureChange = (value: number) => {
    setTempProperties({
      ...tempProperties,
      prompt: {
        ...tempProperties.prompt,
        properties: {
          ...tempProperties.prompt.properties,
          temprature: value.toString(),
        },
      },
    });
  };

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTempProperties({
      ...tempProperties,
      input_key: e.target.value,
    });
  };

  const onInputPlaceholderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTempProperties({
      ...tempProperties,
      input_name: e.target.value,
      input_placeholder: e.target.value,
    });
  };

  const handleConfirm = () => {
    props.onChange(tempProperties);
  };

  return (
    <div className="flex flex-col space-y-2 w-full">
      <div className="flex flex-row items-center space-x-1">
        <label htmlFor="" className="whitespace-nowrap w-[70px] shrink-0">
          输入提示：
        </label>
        <Input
          value={tempProperties.input_name}
          onChange={onInputPlaceholderChange}
          className="w-full"
        ></Input>
      </div>
      <div className="flex flex-row items-center space-x-1">
        <label htmlFor="" className="whitespace-nowrap w-[70px] shrink-0">
          变量名：
        </label>
        <Input
          value={tempProperties.input_key}
          onChange={onInputChange}
          className="w-full"
        ></Input>
      </div>
      <div className="flex flex-row items-center space-x-1">
        <label htmlFor="" className="whitespace-nowrap w-[70px] shrink-0">
          提示词：
        </label>
        <Textarea
          value={tempProperties.prompt.properties.prompt}
          onChange={onValueChange}
          className="w-full"
        ></Textarea>
      </div>
      <div className="flex flex-row items-center space-x-1">
        <label htmlFor="" className="whitespace-nowrap w-[70px] shrink-0">
          指定模型：
        </label>
        <ModelList
          value={tempProperties.prompt.properties.model}
          className="h-8 w-[200px]"
          onChange={onModelChange}
        />
      </div>
      <div className="flex flex-row items-center space-x-1 w-[275px]">
        <label htmlFor="" className="whitespace-nowrap w-[70px] shrink-0">
          设定温度：
        </label>
        <InputNumber
          min={0}
          max={1}
          step={0.1}
          value={Number(tempProperties.prompt?.properties?.temprature)}
          onChange={onTemperatureChange}
          className="w-full"
        ></InputNumber>
      </div>
      <div className="flex flex-row items-center">
        <span className="flex flex-row items-center whitespace-nowrap w-[70px] shrink-0"></span>
        <Button className="h-8 w-20" onClick={handleConfirm}>
          完成
        </Button>
      </div>
    </div>
  );
}
