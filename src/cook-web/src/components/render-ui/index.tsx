'use client';

import Button from './button'
import ButtonView from './view/button'
import Option from './option'
import OptionView from './view/option'
import SingleInput from './input'
import InputView from './view/input'
import Goto from './goto'
import GotoView from './view/goto'
import TextInput from './textinput'
import TextInputView from './view/textinput'
import { useShifu } from '@/store';
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { ChevronDown } from 'lucide-react'
import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '../ui/alert-dialog'
import { useTranslation } from 'react-i18next';

const EditBlockMap = {
    button: Button,
    option: Option,
    goto: Goto,
    phone: SingleInput,
    code: SingleInput,
    textinput: TextInput,
    login: (props) => <Button {...props} mode="login" />,
    payment: (props) => <Button {...props} mode="payment" />,
}

const ViewBlockMap = {
    button: ButtonView,
    option: OptionView,
    goto: GotoView,
    phone: InputView,
    code: InputView,
    textinput: TextInputView,
}

export const BlockUI = ({ id, type, properties, mode = 'edit' }) => {
    const { actions, currentNode, blocks, blockContentTypes, blockUITypes, blockUIProperties, blockContentProperties, currentShifu } = useShifu();
    const [error, setError] = useState('');
    const UITypes = useUITypes()
    const onPropertiesChange = async (properties) => {
        const p = {
            ...blockUIProperties,
            [id]: {
                ...blockUIProperties[id],
                ...properties
            }
        }
        const ut = UITypes.find(p => p.type === type)
        setError('');
        const err = ut?.validate?.(properties)
        if (err) {
            setError(err);
            return;
        }
        if (currentNode) {
            actions.autoSaveBlocks(currentNode.id, blocks, blockContentTypes, blockContentProperties, blockUITypes, p, currentShifu?.shifu_id || '')
        }
    }
    useEffect(() => {
        setError('');
    }, [type]);

    const componentMap = mode === 'edit' ? EditBlockMap : ViewBlockMap
    const Ele = componentMap[type]
    if (!Ele) {
        return null
    }

    return (
        <>
            <Ele
                id={id}
                properties={properties}
                onChange={onPropertiesChange}
            />
            {
                error && (
                    <div className='text-red-500 text-sm px-0 pb-2'>{error}</div>
                )
            }
        </>

    )
}

export const RenderBlockUI = ({ block, mode = 'edit' }) => {
    const {
        actions,
        blockUITypes,
        blockUIProperties,
    } = useShifu();
    const [expand, setExpand] = useState(false)
    const [showConfirmDialog, setShowConfirmDialog] = useState(false)
    const [pendingType, setPendingType] = useState('')
    const { t } = useTranslation();
    const UITypes = useUITypes()
    const onUITypeChange = (id: string, type: string) => {
        if (type === blockUITypes[block.properties.block_id]) {
            return;
        }
        setPendingType(type);
        setShowConfirmDialog(true);
    }

    const handleConfirmChange = () => {
        setExpand(true);
        const opt = UITypes.find(p => p.type === pendingType);
        actions.setBlockUITypesById(block.properties.block_id, pendingType)
        actions.setBlockUIPropertiesById(block.properties.block_id, opt?.properties || {}, true)
        setShowConfirmDialog(false);
    }

    return (
        <>
            <div className='bg-[#F5F5F4] rounded-md p-2 space-y-1'>
                <div className='flex flex-row items-center justify-between py-1 cursor-pointer' onClick={() => setExpand(!expand)}>
                    <div className='flex flex-row items-center space-x-1'>
                        <span>
                            {t('render-ui.user-operation')}
                        </span>
                        <Select value={blockUITypes[block.properties.block_id]} onValueChange={onUITypeChange.bind(null, block.properties.block_id)}>
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

                    <div className='flex flex-row items-center space-x-1 cursor-pointer' onClick={() => setExpand(!expand)}>
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
                        blockUIProperties[block.properties.block_id] && (
                            <BlockUI
                                id={block.properties.block_id}
                                type={blockUITypes[block.properties.block_id]}
                                properties={blockUIProperties[block.properties.block_id]}
                                mode={mode}
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
}

export default RenderBlockUI

export const useUITypes = () => {
    const { t } = useTranslation();
    return [
        {
            type: 'button',
            name: t('render-ui.button'),
            properties: {
            "button_name": t('render-ui.button-button-name'),
            "button_key": t('render-ui.button-button-key')
        },
        validate: (properties): string => {
            if (!properties.button_name) {
                return t('render-ui.button-name-empty')
            }
            return ""
        }
    },
    {
        type: 'option',
        name: t('render-ui.option'),
        properties: {
            "option_name": "",
            "option_key": "",
            "profile_key": "Usage_level",
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
            if (!properties.option_name) {
                return t('render-ui.option-name-empty')
            }
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
        type: 'textinput',
        name: t('render-ui.textinput'),
        properties: {
            "prompt": {
                "properties": {
                    "prompt": "",
                    "profiles": [
                    ],
                    "model": "",
                    "temprature": "0.40",
                    "other_conf": ""
                },
                "type": "ai"
            },
            "input_name": "",
            "input_key": "",
            "input_placeholder": ""
        },
        validate: (properties): string => {
            if (!properties.input_placeholder) {
                return t('render-ui.textinput-placeholder-empty')
            }
            if (!properties.input_key) {
                return t('render-ui.textinput-key-empty')
            }
            if (!properties?.prompt?.properties?.prompt) {
                return t('render-ui.textinput-prompt-empty')
            }
            if (typeof properties?.prompt?.properties?.temprature == 'undefined') {
                return t('render-ui.textinput-temprature-empty')
            }
            if (!properties?.prompt?.properties?.model) {
                return t('render-ui.textinput-model-empty')
            }
            return ""
        }

    },
    /**commit temp  for current version
    {
        type: 'phone',
        name: '手机号',
        properties: {
            "input_name": "",
            "input_key": "",
            "input_placeholder": ""
        },
        validate: (properties): string => {
            if (!properties.input_placeholder) {
                return "提示不能为空"
            }
            if (!properties.input_key) {
                return "名称不能为空"
            }
            return "";
        }
    },
    {
        type: 'code',
        name: '手机验证码',
        properties: {
            "input_name": "",
            "input_key": "",
            "input_placeholder": ""
        },
        validate: (properties): string => {
            if (!properties.input_placeholder) {
                return "提示不能为空"
            }
            if (!properties.input_key) {
                return "名称不能为空"
            }
            return "";
        }
    }, **/
    {
        type: 'login',
        name: t('render-ui.login'),
        properties: {
            "button_name": "",
            "button_key": ""
        },
        validate: (properties): string => {
            if (!properties.button_name) {
                return t('render-ui.login-button-name-empty')
            }
            return ""
        }
    },
    {
        type: 'payment',
        name: t('render-ui.payment'),
        properties: {
            "button_name": "",
            "button_key": ""
        },
        validate: (properties): string => {
            if (!properties.button_name) {
                return t('render-ui.payment-button-name-empty')
            }
            return ""
        }
    },
    ]
}
