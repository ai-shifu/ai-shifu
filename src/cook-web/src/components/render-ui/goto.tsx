import React, { useEffect, useState } from 'react';

import OutlineSelector from '@/components/outline-selector';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { useScenario } from '@/store';
import { Outline } from '@/types/scenario';
import api from '@/api';
import { Button } from '../ui/button';

interface ColorSetting {
  color: string;
  text_color: string;
}

interface ProfileItemDefination {
  color_setting: ColorSetting;
  profile_key: string;
  profile_id: string;
}

interface GotoProps {
  properties: {
    goto_settings: {
      items: {
        value: string;
        type: string;
        goto_id: string;
      }[];
      profile_key: string;
    };
    button_name: string;
    button_key: string;
  };
  onChange: (properties: any) => void;
}

export default function Goto(props: GotoProps) {
  const { properties } = props;
  const { chapters, currentScenario } = useScenario();

  const [profileItemDefinations, setProfileItemDefinations] = useState<
    ProfileItemDefination[]
  >([]);
  const [selectedProfile, setSelectedProfile] =
    useState<ProfileItemDefination | null>(null);
  const [tempGotoSettings, setTempGotoSettings] = useState(
    properties.goto_settings,
  );

  const onNodeSelect = (index: number, node: Outline) => {
    setTempGotoSettings({
      ...tempGotoSettings,
      items: tempGotoSettings.items.map((item, i) => {
        if (i === index) {
          return {
            ...item,
            goto_id: node.id,
          };
        }
        return item;
      }),
    });
  };

  const handleConfirm = () => {
    props.onChange({
      ...properties,
      goto_settings: tempGotoSettings,
    });
  };

  const loadProfileItemDefinations = async (
    preserveSelection: boolean = false,
  ) => {
    const list = await api.getProfileItemDefinitions({
      parent_id: currentScenario?.id,
    });
    setProfileItemDefinations(list);

    if (!preserveSelection && list.length > 0) {
      const initialSelected = list.find(
        (item) => item.profile_key === properties.goto_settings.profile_key,
      );
      if (initialSelected) {
        setSelectedProfile(initialSelected);
        await loadProfileItem(
          initialSelected.profile_id,
          initialSelected.profile_key,
        );
      }
    }
  };

  const loadProfileItem = async (id: string, name: string) => {
    const list = await api.getProfileItemOptionList({
      parent_id: id,
    });
    // 更新临时变量
    setTempGotoSettings({
      profile_key: name,
      items: list.map((item) => {
        return {
          value: item.value,
          goto_id: '',
          type: 'goto',
        };
      }),
    });
  };

  useEffect(() => {
    loadProfileItemDefinations();
  }, []);

  const handleValueChange = async (value: string) => {
    const selectedItem = profileItemDefinations.find(
      (item) => item.profile_id === value,
    );
    if (selectedItem) {
      setSelectedProfile(selectedItem);
      await loadProfileItem(value, selectedItem.profile_key);
    }
  };

  return (
    <div className="flex flex-col space-y-1">
      <div className="flex flex-row items-center space-x-1">
        <div className="flex flex-row whitespace-nowrap w-[70px] shrink-0">
          变量选择：
        </div>
        <Select
          value={selectedProfile?.profile_id || ''}
          onValueChange={handleValueChange}
          onOpenChange={(open) => {
            if (open) {
              loadProfileItemDefinations(true);
            }
          }}
        >
          <SelectTrigger className="h-8 w-[170px]">
            <SelectValue>
              {selectedProfile?.profile_key || '选择变量'}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {profileItemDefinations?.map((item) => {
              return (
                <SelectItem key={item.profile_key} value={item.profile_id}>
                  {item.profile_key}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-row items-start py-2">
        <div className="flex flex-row whitespace-nowrap w-[70px] shrink-0">
          跳转位置：
        </div>
        <div className="flex flex-col space-y-1 ">
          {tempGotoSettings.items.map((item, index) => {
            return (
              <div
                className="flex flex-row items-center space-x-2"
                key={`${item.value}-${index}`}
              >
                <span className="w-40">{item.value}</span>
                <span className="px-2">跳转到</span>
                <span>
                  <OutlineSelector
                    value={item.goto_id}
                    chapters={chapters}
                    onSelect={onNodeSelect.bind(null, index)}
                  />
                </span>
              </div>
            );
          })}
        </div>
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
