import React from 'react';

interface InputViewProps {
  properties: {
    input_name: string;
    input_key: string;
    input_placeholder: string;
  };
}

export default function InputView(props: InputViewProps) {
  const { properties } = props;
  return (
    <div className="flex flex-col space-y-2">
      <div className="flex flex-row items-center space-x-1">
        <span className="whitespace-nowrap">提示：</span>
        <div className="px-3 py-2 bg-gray-50 rounded-md">
          {properties.input_placeholder}
        </div>
      </div>
      <div className="flex flex-row items-center space-x-1">
        <span className="whitespace-nowrap">变量名：</span>
        <div className="px-3 py-2 bg-gray-50 rounded-md">
          {properties.input_key}
        </div>
      </div>
      <div className="flex flex-row items-center space-x-1">
        <span className="whitespace-nowrap">名称：</span>
        <div className="px-3 py-2 bg-gray-50 rounded-md">
          {properties.input_name}
        </div>
      </div>
    </div>
  );
}
