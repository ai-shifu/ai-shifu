import React, { memo, useEffect, useState } from 'react';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { useTranslation } from 'react-i18next';
import _ from 'lodash';
import { OptionsDTO, ProfileItemDefination, UIBlockDTO } from '@/types/shifu';
import i18n from '@/i18n';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/Select';
import { useShifu } from '@/store';
import api from '@/api';

const OptionPropsEqual = (prevProps: UIBlockDTO, nextProps: UIBlockDTO) => {
  const prevOptionsSettings = prevProps.data.properties as OptionsDTO;
  const nextOptionsSettings = nextProps.data.properties as OptionsDTO;
  if (!_.isEqual(prevProps.data, nextProps.data)) {
    return false;
  }
  if (
    !_.isEqual(
      prevOptionsSettings.result_variable_bid,
      nextOptionsSettings.result_variable_bid,
    )
  ) {
    return false;
  }
  for (let i = 0; i < prevOptionsSettings.options.length; i++) {
    if (
      !_.isEqual(prevOptionsSettings.options[i], nextOptionsSettings.options[i])
    ) {
      return false;
    }
  }
  return true;
};

export default memo(function Option(props: UIBlockDTO) {
  const { data, onChanged } = props;
  const { currentShifu } = useShifu();
  const { t } = useTranslation();
  const [changed, setChanged] = useState(false);
  const optionsSettings = data.properties as OptionsDTO;
  const [tempOptions, setTempOptions] = useState(optionsSettings.options);
  const [selectedProfile, setSelectedProfile] =
    useState<ProfileItemDefination | null>(null);
  const [profileItemDefinations, setProfileItemDefinations] = useState<
    ProfileItemDefination[]
  >([]);
  const [variableBid, setVariableBid] = useState<string>(
    optionsSettings.result_variable_bid,
  );

  const onButtonTextChange = (
    index: number,
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    setTempOptions(
      tempOptions.map((option: any, i: number) => {
        if (i === index) {
          return {
            ...option,
            label: {
              ...option.label,
              lang: {
                ...option.label.lang,
                'zh-CN': e.target.value,
                'en-US': e.target.value,
              },
            },
          };
        }
        return option;
      }),
    );
  };

  const handleConfirm = () => {
    if (tempOptions.length === 0) {
      const defaultButton = {
        value: t('option.buttonKey'),
        label: {
          lang: {
            'zh-CN': t('option.buttonText'),
            'en-US': t('option.buttonText'),
          },
        },
      };
      setTempOptions([defaultButton]);
    }

    const updatedProperties = {
      ...data,
      properties: {
        ...data.properties,
        options: tempOptions,
        result_variable_bid: variableBid,
      },
      variable_bids: [variableBid],
    };
    props.onPropertiesChange(updatedProperties);
  };

  const handleValueChange = async (value: string) => {
    setVariableBid(value);
    if (!changed) {
      setChanged(true);
      onChanged?.(true);
    }
    const selectedItem = profileItemDefinations.find(
      item => item.profile_id === value,
    );
    if (selectedItem) {
      setSelectedProfile(selectedItem);
      await loadProfileItem(value);
    }
  };
  useEffect(() => {
    loadProfileItemDefinations();
  }, []);
  const loadProfileItem = async (id: string) => {
    setVariableBid(id);
    const list = await api.getProfileItemOptionList({
      parent_id: id,
    });
    const options = list.map(item => {
      const existingOption = tempOptions.find(
        option => option.value === item.value,
      );
      if (existingOption) {
        return existingOption;
      }
      return {
        value: item.value,
        label: {
          lang: {
            'zh-CN': item.value,
            'en-US': item.value,
          },
        },
      };
    });

    setTempOptions(options);
  };

  const loadProfileItemDefinations = async (
    preserveSelection: boolean = false,
  ) => {
    const list = await api.getProfileItemDefinitions({
      parent_id: currentShifu?.bid,
      type: 'option',
    });
    setProfileItemDefinations(list);
    if (!preserveSelection && list.length > 0) {
      const initialSelected = list.find(
        item => item.profile_id === variableBid,
      );
      if (initialSelected) {
        setSelectedProfile(initialSelected);
        await loadProfileItem(initialSelected.profile_id);
      }
    }
  };

  return (
    <div className='flex flex-col space-y-1 space-x-1'>
      <div className='flex flex-row items-center'>
        <label
          htmlFor=''
          className='whitespace-nowrap w-[70px] shrink-0'
        >
          {t('option.variable')}
        </label>
        <Select
          value={selectedProfile?.profile_key || ''}
          onValueChange={handleValueChange}
          onOpenChange={open => {
            if (open) {
              loadProfileItemDefinations(true);
            }
          }}
        >
          <SelectTrigger className='h-8 w-[170px]'>
            <SelectValue>
              {selectedProfile?.profile_key || t('option.selectVariable')}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {profileItemDefinations?.map(item => {
              return (
                <SelectItem
                  key={item.profile_key}
                  value={item.profile_id}
                >
                  {item.profile_key}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
      </div>
      <div className='flex flex-col space-y-2'>
        {tempOptions.map((option: any, index: number) => {
          return (
            <div
              key={index}
              className='flex flex-row items-center'
            >
              <label
                htmlFor=''
                className='whitespace-nowrap w-[70px] shrink-0'
              >
                {t('option.value')}
              </label>
              <label>{option.value}</label>
              <label
                htmlFor=''
                className='whitespace-nowrap w-[50px] shrink-0 ml-4'
              >
                {t('option.title')}
              </label>
              <Input
                value={option.label.lang[i18n.language]}
                className='w-40 ml-4'
                onChange={onButtonTextChange.bind(null, index)}
              ></Input>
            </div>
          );
        })}
      </div>
      <div className='flex flex-row items-center'>
        <label
          htmlFor=''
          className='whitespace-nowrap w-[70px] shrink-0'
        ></label>
        <Button
          className='h-8 w-20'
          onClick={handleConfirm}
        >
          {t('option.complete')}
        </Button>
      </div>
    </div>
  );
}, OptionPropsEqual);
