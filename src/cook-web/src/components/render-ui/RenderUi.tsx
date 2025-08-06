'use client';

import Button from './button';
// import ButtonView from './view/button'
import Option from './option';
// import OptionView from './view/option'
import SingleInput from './input';
// import InputView from './view/input'
import Goto from './goto';
// import GotoView from './view/goto'
import TextInput from './TextInput';
// import TextInputView from './view/TextInput'
import { RenderBlockContent } from '../render-block/index';
import { useShifu } from '@/store';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/Select';
import { ChevronDown } from 'lucide-react';
import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../ui/AlertDialog';
import { useTranslation } from 'react-i18next';
import { memo } from 'react';
import Empty from './empty';
import _ from 'lodash';
import { BlockDTO, UIBlockDTO } from '@/types/shifu';
import i18n from '@/i18n';
const componentMap = {
  content: RenderBlockContent,
  input: TextInput,
  button: Button,
  options: Option,
  goto: Goto,
  phone: SingleInput,
  code: SingleInput,
  option: Option,
  textinput: TextInput,
  login: props => (
    <Button
      {...props}
      mode='login'
    />
  ),
  payment: props => (
    <Button
      {...props}
      mode='payment'
    />
  ),
  empty: Empty,
};

const BlockUIPropsEqual = (prevProps: UIBlockDTO, nextProps: UIBlockDTO) => {
  if (
    !_.isEqual(prevProps.id, nextProps.id) ||
    prevProps.data.type !== nextProps.data.type
  ) {
    return false;
  }
  if (!_.isEqual(prevProps.data.properties, nextProps.data.properties)) {
    return false;
  }
  if (!_.isEqual(prevProps.data.variable_bids, nextProps.data.variable_bids)) {
    return false;
  }
  if (!_.isEqual(prevProps.data.resource_bids, nextProps.data.resource_bids)) {
    return false;
  }
  return true;
};
export const BlockUI = memo(function BlockUI(p: UIBlockDTO) {
  const { id, data, onChanged } = p;
  const {
    actions,
    currentNode,
    blocks,
    blockTypes,
    blockProperties,
    currentShifu,
  } = useShifu();
  const [error, setError] = useState('');
  const UITypes = useUITypes();
  const handleChanged = (changed: boolean) => {
    onChanged?.(changed);
  };

  const onPropertiesChange = async properties => {
    const p = {
      ...blockProperties,
      [id]: {
        ...blockProperties[id],
        ...properties,
      },
    };
    const ut = UITypes.find(p => p.type === data.type);
    setError('');
    const err = ut?.validate?.(properties);
    if (err) {
      setError(err);
      return;
    }
    await actions.updateBlockProperties(id, properties);

    const newBlocks = blocks.map(b =>
      b.bid === id ? { ...b, properties: properties } : b,
    );
    const newBlockTypes = {
      ...blockTypes,
      [id]: data.type,
    };
    if (currentNode) {
      actions.autoSaveBlocks(
        currentNode.bid,
        newBlocks,
        newBlockTypes,
        p,
        currentShifu?.bid || '',
      );
    }
  };

  useEffect(() => {
    setError('');
  }, [data.type]);

  const Ele = componentMap[data.type];
  if (!Ele) {
    return null;
  }
  return (
    <>
      <Ele
        {...{
          id: id,
          data: data,
          onPropertiesChange: onPropertiesChange,
          onChanged: handleChanged,
          onEditChange: () => {},
          isEdit: false,
          isChanged: false,
        }}
      />
      {error && <div className='text-red-500 text-sm px-0 pb-2'>{error}</div>}
    </>
  );
}, BlockUIPropsEqual);

export const RenderBlockUI = memo(
  function RenderBlockUI({
    block,
    onExpandChange,
    expanded,
  }: {
    block: BlockDTO;
    onExpandChange?: (expanded: boolean) => void;
    expanded?: boolean;
  }) {
    const {
      actions,
      currentNode,
      blockProperties,
      blockTypes,
      blocks,
      currentShifu,
    } = useShifu();

    if (expanded === undefined) {
      expanded = block.type === 'content' ? true : false;
    }
    const [expand, setExpand] = useState(expanded);
    const [showConfirmDialog, setShowConfirmDialog] = useState(false);
    const [pendingType, setPendingType] = useState('');
    const [isChanged, setIsChanged] = useState(false);
    const { t } = useTranslation();
    const UITypes = useUITypes();
    const handleExpandChange = (newExpand: boolean) => {
      setExpand(newExpand);
      onExpandChange?.(newExpand);
    };

    const handleTypeChange = async (type: string) => {
      handleExpandChange(true);
      const opt = UITypes.find(p => p.type === type);
      const p = {
        ...blockProperties,
        [block.bid]: {
          ...blockProperties[block.bid],
          type: type,
          properties: opt?.properties || {},
        },
      };
      await actions.updateBlockProperties(block.bid, {
        bid: block.bid,
        type: type,
        variable_bids: [],
        result_variable_bid: '',
        properties: opt?.properties || {},
      });
      setIsChanged(false);

      const newBlocks = blocks.map(b =>
        b.bid === block.bid
          ? { ...b, type: type, properties: opt?.properties || {} }
          : b,
      );
      const newBlockTypes = {
        ...blockTypes,
        [block.bid]: type,
      };
      if (currentNode) {
        await actions.autoSaveBlocks(
          currentNode.bid,
          newBlocks,
          newBlockTypes,
          p,
          currentShifu?.bid || '',
        );
      }
    };

    const onUITypeChange = (id: string, type: string) => {
      const isChanged = type !== blockTypes[block.bid];
      if (isChanged) {
        setPendingType(type);
        setShowConfirmDialog(true);
      } else {
        handleTypeChange(type);
      }
    };

    const handleConfirmChange = () => {
      handleTypeChange(pendingType);
      setShowConfirmDialog(false);
    };

    const handleBlockChanged = (changed: boolean) => {
      if (changed !== isChanged) {
        setIsChanged(changed);
      }
    };

    const onPropertiesChange = properties => {
      console.log('onPropertiesChange', properties);
    };

    const handleBlockEditChange = (isEdit: boolean) => {
      setExpand(isEdit);
    };

    return (
      <>
        <div className='bg-[#F8F8F8] rounded-md p-2 space-y-1'>
          <div
            className='flex flex-row items-center justify-between py-1 cursor-pointer'
            onClick={() => handleExpandChange(!expand)}
          >
            <div className='flex flex-row items-center space-x-1'>
              <span className='w-[70px]'>{t('renderUi.userOperation')}</span>
              <Select
                value={blockProperties[block.bid].type}
                onValueChange={onUITypeChange.bind(null, block.bid)}
              >
                <SelectTrigger className='h-8 w-[120px]'>
                  <SelectValue placeholder={t('renderUi.selectPlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {UITypes.map(item => {
                      return (
                        <SelectItem
                          key={item.type}
                          value={item.type}
                        >
                          {item.name}
                        </SelectItem>
                      );
                    })}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>

            <div
              className='flex flex-row items-center space-x-1 cursor-pointer'
              onClick={() => handleExpandChange(!expand)}
            >
              <ChevronDown
                className={cn(
                  'h-5 w-5 transition-transform duration-200 ease-in-out',
                  expand ? 'rotate-180' : '',
                )}
              />
              {expand ? t('renderUi.collapse') : t('renderUi.expand')}
            </div>
          </div>
          <div className={cn('space-y-1', expand ? 'block' : 'hidden')}>
            {blockProperties[block.bid] && (
              <BlockUI
                id={block.bid}
                data={block}
                onChanged={handleBlockChanged}
                onPropertiesChange={onPropertiesChange}
                isEdit={expand}
                isChanged={isChanged}
                onEditChange={handleBlockEditChange}
              />
            )}
          </div>
        </div>

        <AlertDialog
          open={showConfirmDialog}
          onOpenChange={setShowConfirmDialog}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('renderUi.confirmChange')}</AlertDialogTitle>
              <AlertDialogDescription>
                {t('renderUi.confirmChangeDescription')}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t('renderUi.cancel')}</AlertDialogCancel>
              <AlertDialogAction onClick={handleConfirmChange}>
                {t('renderUi.confirm')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </>
    );
  },
  (prevProps, nextProps) => {
    return (
      prevProps.block.bid === nextProps.block.bid &&
      prevProps.onExpandChange === nextProps.onExpandChange
    );
  },
);
RenderBlockUI.displayName = 'RenderBlockUI';

export default RenderBlockUI;

export const useUITypes = () => {
  const { t } = useTranslation();
  return [
    {
      type: 'button',
      name: t('renderUi.button'),
      properties: {
        label: {
          lang: {
            'zh-CN': t('renderUi.buttonText'),
            'en-US': t('renderUi.buttonText'),
          },
        },
      },
    },
    {
      type: 'options',
      name: t('renderUi.option'),
      properties: {
        options: [
          {
            label: {
              lang: {
                'zh-CN': t('renderUi.buttonText'),
                'en-US': t('renderUi.buttonText'),
              },
            },
            value: t('renderUi.buttonKey'),
          },
        ],
        result_variable_bid: '',
      },
      validate: (data): string => {
        if (data.properties.options.length === 0) {
          return t('renderUi.optionButtonsEmpty');
        }
        for (let i = 0; i < data.properties.options.length; i++) {
          const item = data.properties.options[i];
          if (!item.value || item.label.lang[i18n.language] == '') {
            return t('renderUi.optionButtonEmpty');
          }
        }
        return '';
      },
    },
    {
      type: 'goto',
      name: t('renderUi.goto'),
      properties: {
        conditions: [
          {
            value: '',
            destination_type: '',
            destination_bid: '',
          },
        ],
      },
    },
    {
      type: 'input',
      name: t('renderUi.textInput'),

      properties: {
        placeholder: {
          lang: {
            'zh-CN': '',
            'en-US': '',
          },
        },
        prompt: '',
        result_variable_bids: [],
        llm: '',
        llm_temperature: '0.40',
      },
      validate: (data): string => {
        const p = data.properties;

        if (!p.placeholder.lang[i18n.language]) {
          return t('renderUi.textInputPlaceholderEmpty');
        }
        if (!p?.prompt) {
          return t('renderUi.textInputPromptEmpty');
        }
        if (typeof p?.llm_temperature == 'undefined') {
          return t('renderUi.textInputTemperatureEmpty');
        }
        return '';
      },
    },
    {
      type: 'login',
      name: t('renderUi.login'),
      properties: {
        label: {
          lang: {
            'zh-CN': '',
            'en-US': '',
          },
        },
      },
    },
    {
      type: 'payment',
      name: t('renderUi.payment'),
      properties: {
        label: {
          lang: {
            'zh-CN': '',
            'en-US': '',
          },
        },
      },
    },
    {
      type: 'content',
      name: t('renderUi.content'),
      properties: {
        content: '',
        llm: '',
        llm_temperature: 0.4,
        llm_enabled: true,
      },
      validate: (data): string => {
        if (!data.properties.content) {
          return t('renderUi.contentEmpty');
        }
        return '';
      },
    },
  ];
};
