'use client';

import Button from './button'
// import ButtonView from './view/button'
import Option from './option'
// import OptionView from './view/option'
import SingleInput from './input'
// import InputView from './view/input'
import Goto from './goto'
// import GotoView from './view/goto'
import TextInput from './textinput'
// import TextInputView from './view/textinput'
import {RenderBlockContent} from '../render-block/index'
import Break from './break'
import { useShifu } from '@/store';
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { ChevronDown } from 'lucide-react'
import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '../ui/alert-dialog'
import { useTranslation } from 'react-i18next';
import { memo } from 'react'
import Empty from './empty'
import _ from 'lodash'
import { BlockDTO, UIBlockDTO } from '@/types/shifu';
const componentMap = {
    content: RenderBlockContent,
    break: Break,
    input: TextInput,
    button: Button,
    options: Option,
    goto: Goto,
    phone: SingleInput,
    code: SingleInput,
    // old
    option:  Option,
    textinput: TextInput,
    login: (props) => <Button {...props} mode="login" />,
    payment: (props) => <Button {...props} mode="payment" />,
    empty: Empty,
}

const BlockUIPropsEqual = (prevProps: any, nextProps: any) => {
    if (! _.isEqual(prevProps.id, nextProps.id) || prevProps.type !== nextProps.type) {
        return false
    }
    const prevKeys = Object.keys(prevProps.properties || {})
    const nextKeys = Object.keys(nextProps.properties || {})
    if (prevKeys.length !== nextKeys.length) {
        return false
    }
    if (!_.isEqual(prevProps.properties, nextProps.properties)) {
        return false
    }
    return true
}
export const BlockUI = memo(function BlockUI(p: UIBlockDTO){
    const { id, data, onChanged } = p
    const { actions, currentNode, blocks, blockTypes, blockProperties, currentShifu } = useShifu();
    const [error, setError] = useState('');
    const UITypes = useUITypes()
    const handleChanged = (changed: boolean) => {
        onChanged?.(changed);
    }

    const onPropertiesChange = async (properties) => {
        const p = {
            ...blockProperties,
            [id]: {
                ...blockProperties[id],
                ...properties
            }
        }
        const ut = UITypes.find(p => p.type === data.type)
        setError('');
        const err = ut?.validate?.(properties)
        if (err) {
            setError(err);
            return;
        }
        actions.updateBlockProperties(id, properties);
        if (currentNode) {
            actions.autoSaveBlocks(currentNode.id, blocks, blockTypes, p, currentShifu?.bid || '')
        }
    }

    useEffect(() => {
        setError('');
    }, [data.type]);

    const Ele = componentMap[data.type]
    if (!Ele) {
        return null
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
                    isChanged: false
                }}
            />
            {
                error && (
                    <div className='text-red-500 text-sm px-0 pb-2'>{error}</div>
                )
            }
        </>
    )
}, BlockUIPropsEqual)

export const RenderBlockUI = memo(function RenderBlockUI({ block, onExpandChange }: { block: BlockDTO, onExpandChange?: (expanded: boolean) => void }) {
    const {
        actions,
        blockUITypes,
        blockUIProperties,
        currentNode,
        blocks,
        blockContentTypes,
        blockContentProperties,
        currentShifu,
        blockProperties,
    } = useShifu();
    const [expand, setExpand] = useState(false)
    const [showConfirmDialog, setShowConfirmDialog] = useState(false)
    const [pendingType, setPendingType] = useState('')
    const [isChanged, setIsChanged] = useState(false)
    const { t } = useTranslation();
    const UITypes = useUITypes()
    const handleExpandChange = (newExpand: boolean) => {
        setExpand(newExpand)
        onExpandChange?.(newExpand)
    }

    const handleTypeChange = (type: string) => {
        handleExpandChange(true);
        const opt = UITypes.find(p => p.type === type);
        actions.setBlockUITypesById(block.id, type)
        actions.setBlockUIPropertiesById(block.id, opt?.properties || {}, true)

        const newUITypes = {
            ...blockUITypes,
            [block.id]: type,
        }
        const newUIProps = {
            ...blockUIProperties,
            [block.id]: opt?.properties || {},
        }

        setIsChanged(false);

        if (['login', 'payment', 'empty'].includes(type) && currentNode) {
            actions.autoSaveBlocks(
                currentNode.id,
                blocks,
                blockContentTypes,
                blockContentProperties,
                newUITypes,
                newUIProps,
                currentShifu?.bid || ''
            )
        }
    }

    const onUITypeChange = (id: string, type: string) => {
        if (type === blockUITypes[block.properties.block_id]) {
            return;
        }
        if (isChanged) {
            setPendingType(type);
            setShowConfirmDialog(true);
        } else {
            handleTypeChange(type);
        }
    }

    const handleConfirmChange = () => {
        handleTypeChange(pendingType);
        setShowConfirmDialog(false);
    }

    const handleBlockChanged = (changed: boolean) => {
        if (changed !== isChanged) {
            setIsChanged(changed);
        }
    }

    const onPropertiesChange = (properties) => {
        console.log('onPropertiesChange',properties)
    }

    const handleBlockEditChange = (isEdit: boolean) => {
        setExpand(isEdit);
    }

    return (
        <>
            <div className='bg-[#F8F8F8] rounded-md p-2 space-y-1'>
                <div className='flex flex-row items-center justify-between py-1 cursor-pointer' onClick={() => handleExpandChange(!expand)}>
                    <div className='flex flex-row items-center space-x-1'>
                        <span className='w-[70px]'>
                            {t('render-ui.user-operation')}
                        </span>
                        <Select value={blockProperties[block.bid].type} onValueChange={onUITypeChange.bind(null, block.bid)}>
                            <SelectTrigger className="h-8 w-[120px]">
                                <SelectValue placeholder={t('render-ui.select-placeholder')} />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectGroup>
                                    {
                                        UITypes.map((item) => {
                                            return (
                                                <SelectItem key={item.type} value={item.type}>{item.name}</SelectItem>
                                            )
                                        })
                                    }
                                </SelectGroup>
                            </SelectContent>
                        </Select>
                    </div>

                    <div className='flex flex-row items-center space-x-1 cursor-pointer' onClick={() => handleExpandChange(!expand)}>
                        <ChevronDown className={cn(
                            "h-5 w-5 transition-transform duration-200 ease-in-out",
                            expand ? 'rotate-180' : ''
                        )} />
                        {
                            expand ? t('render-ui.collapse') : t('render-ui.expand')
                        }
                    </div>
                </div>
                <div className={cn(
                    'space-y-1',
                    expand ? 'block' : 'hidden'
                )}>
                    {
                        blockProperties[block.bid] && (
                            <BlockUI
                                id={block.bid}
                                data={block}
                                onChanged={handleBlockChanged}
                                onPropertiesChange={onPropertiesChange}
                                isEdit={expand}
                                isChanged={isChanged}
                                onEditChange={handleBlockEditChange}
                            />
                        )
                    }
                </div>
            </div>

            <AlertDialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>{t('render-ui.confirm-change')}</AlertDialogTitle>
                        <AlertDialogDescription>
                            {t('render-ui.confirm-change-description')}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>{t('render-ui.cancel')}</AlertDialogCancel>
                        <AlertDialogAction onClick={handleConfirmChange}>{t('render-ui.confirm')}</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </>
    )
}, (prevProps, nextProps) => {
    return prevProps.block.id === nextProps.block.id && prevProps.onExpandChange === nextProps.onExpandChange
})
RenderBlockUI.displayName = 'RenderBlockUI'

export default RenderBlockUI

export const useUITypes = () => {
    const { t } = useTranslation();
    return [
    {
        type: 'button',
        name: t('render-ui.button'),
        properties: {
            "label": {
                "lang": {
                    "zh-CN": t('render-ui.button-name'),
                    "en-US": t('render-ui.button-name')
                }
            },
        }
    },
    {
        type: 'options',
        name: t('render-ui.option'),
        properties: {
            "profile_id": "",
            "buttons": [
                {
                    "properties": {
                        "button_name": t('render-ui.button-name'),
                        "button_key": t('render-ui.button-key')
                    },
                    "type": "button"
                }
            ]
        },
        validate: (properties): string => {
            // if (!properties.option_name) {
            //     return t('render-ui.option-name-empty')
            // }
            if (properties.buttons.length === 0) {
                return t('render-ui.option-buttons-empty')
            }
            for (let i = 0; i < properties.buttons.length; i++) {
                const item = properties.buttons[i];
                if (!item.properties.button_key || item.properties.button_name == "") {
                    return t('render-ui.option-button-empty')
                }
            }
            return ""
        }
    },
    {
        type: 'goto',
        name: t('render-ui.goto'),
        properties: {
            "goto_settings": {
                "items": [
                    {
                        "value": t('render-ui.goto-value'),
                        "type": "outline",
                        "goto_id": "tblDUfFbHGnM4LQl"
                    },
                    {
                        "value": t('render-ui.goto-value'),
                        "type": "outline",
                        "goto_id": "tbl9gl38im3rd1HB"
                    }
                ],
                "profile_key": "ai_tools"
            },
            "button_name": t('render-ui.goto-button-name'),
            "button_key": t('render-ui.goto-button-key')
        }
    },
    {
        type: 'input',
        name: t('render-ui.textinput'),
        properties: {
            "prompt": {
                "properties": {
                    "prompt": "",
                    "variables": [
                    ],
                    "model": "",
                    "temperature": "0.40",
                    "other_conf": ""
                },
                "type": "ai"
            },
            "input_name": "",
            "input_key": "",
            "input_placeholder": "",
            "profile_ids": []
        },
        validate: (properties): string => {
            if (!properties.input_placeholder) {
                return t('render-ui.textinput-placeholder-empty')
            }
            if (!properties?.prompt?.properties?.prompt) {
                return t('render-ui.textinput-prompt-empty')
            }
            if (typeof properties?.prompt?.properties?.temperature == 'undefined') {
                return t('render-ui.textinput-temperature-empty')
            }
            return ""
        }

    },
    {
        type: 'empty',
        name: t('render-ui.none'),
        properties: {},
    },
    {
        type: 'login',
        name: t('render-ui.login'),
        properties: {
            "button_name": "",
            "button_key": ""
        }
    },
    {
        type: 'payment',
        name: t('render-ui.payment'),
        properties: {
            "button_name": "",
            "button_key": ""
        }
    },
    {
        type: 'content',
        name: t('render-ui.content'),
        properties: {
            "content": ""
        }
    }
    ]
}
