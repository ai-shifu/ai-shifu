import Button from './button'
import Option from './option'

import SingleInput from './input'
import Goto from './goto'
import TextInput from './textinput'

import { useScenario } from '@/store';
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/utils'


const BlockMap = {
    button: Button,
    option: Option,
    goto: Goto,
    phone: SingleInput,
    code: SingleInput,
    textinput: TextInput,
}

export const BlockUI = ({ id, type, properties }) => {
    const { actions, currentOutline, blocks, blockContentTypes, blockUITypes, blockUIProperties, blockContentProperties } = useScenario();
    const onPropertiesChange = async (properties) => {
        await actions.setBlockUIPropertiesById(id, properties)
        const p = {
            ...blockUIProperties,
            [id]: {
                ...blockUIProperties[id],
                ...properties
            }
        }
        actions.autoSaveBlocks(currentOutline, blocks, blockContentTypes, blockContentProperties, blockUITypes, p)
    }
    const Ele = BlockMap[type]
    if (!Ele) {
        // console.log('type', type)
        return null
    }
    return (
        <Ele
            properties={properties}
            onChange={onPropertiesChange}
        />
    )
}

export const RenderBlockUI = ({ block }) => {
    const {
        actions,
        blockUITypes,
        blockUIProperties,
    } = useScenario();
    const [expand, setExpand] = useState(false)

    const onUITypeChange = (id: string, type: string) => {
        setExpand(true);
        const opt = UITypes.find(p => p.type === type);
        actions.setBlockUITypesById(id, type)
        actions.setBlockUIPropertiesById(id, opt?.properties || {})
    }
    return (
        <>
            <div className='bg-[#F5F5F4] rounded-md p-2 space-y-1'>
                <div className=' flex flex-row items-center justify-between py-1 cursor-pointer' onClick={() => setExpand(!expand)}>
                    <div className='flex flex-row items-center space-x-1'>
                        <span>
                            用户操作：
                        </span>
                        <Select value={blockUITypes[block.properties.block_id]} onValueChange={onUITypeChange.bind(null, block.properties.block_id)}>
                            <SelectTrigger className=" h-8 w-[120px]">
                                <SelectValue placeholder="请选择" />
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
                            " h-5 w-5 transition-transform duration-200 ease-in-out",
                            expand ? 'rotate-180' : ''
                        )} />
                        {
                            expand ? "收起" : "展开"
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
                            />
                        )
                    }
                </div>
            </div>
        </>
    )
}

export default RenderBlockUI

export const UITypes = [
    {
        type: 'button',
        name: '按钮',
        properties: {
            "button_name": "继续",
            "button_key": "继续"
        }
    },
    {
        type: 'option',
        name: '按钮组',
        properties: {
            "option_name": "",
            "option_key": "",
            "profile_key": "Usage_level",
            "buttons": [
                {
                    "properties": {
                        "button_name": "全部",
                        "button_key": "全部"
                    },
                    "type": "button"
                }
            ]
        }
    },
    {
        type: 'goto',
        name: '跳转',
        properties: {
            "goto_settings": {
                "items": [
                    {
                        "value": "通义灵码",
                        "type": "outline",
                        "goto_id": "tblDUfFbHGnM4LQl"
                    },
                    {
                        "value": "GitHub_Copilot",
                        "type": "outline",
                        "goto_id": "tbl9gl38im3rd1HB"
                    }
                ],
                "profile_key": "ai_tools"
            },
            "button_name": "来吧",
            "button_key": "来吧"
        }
    },
    {
        type: 'textinput',
        name: '输入框',
        properties: {
            "prompt": {
                "properties": {
                    "prompt": "",
                    "profiles": [
                        "user_background"
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
        }
    },
    {
        type: 'phone',
        name: '手机号',
        properties: {
            "input_name": "",
            "input_key": "",
            "input_placeholder": "输入手机号"
        }
    },
    {
        type: 'code',
        name: '手机验证码',
        properties: {
            "input_name": "请输入4位数字验证码",
            "input_key": "请输入4位数字验证码",
            "input_placeholder": "请输入4位数字验证码"
        }
    },

]
