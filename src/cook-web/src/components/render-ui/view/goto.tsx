import React from 'react';

interface GotoViewProps {
  properties: {
    goto_settings: {
      items: Array<{
        value: string;
        type: string;
        goto_id: string;
      }>;
      profile_key: string;
    };
    button_name: string;
    button_key: string;
  };
}

export default function GotoView(props: GotoViewProps) {
  const { properties } = props;
  return (
    <div className="flex flex-col space-y-2">
      <div className="flex flex-row items-center space-x-1">
        <span className="whitespace-nowrap">跳转选项：</span>
        <div className="flex flex-col space-y-1 bg-gray-50 rounded-md p-2">
          {properties.goto_settings.items.map((item, index) => (
            <div key={index} className="px-3 py-2 bg-gray-100 rounded-md">
              {item.value}
            </div>
          ))}
        </div>
      </div>
      <div className="flex flex-row items-center space-x-1">
        <span className="whitespace-nowrap">按钮文案：</span>
        <button
          className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md cursor-default"
          disabled
        >
          {properties.button_name}
        </button>
      </div>
    </div>
  );
}
