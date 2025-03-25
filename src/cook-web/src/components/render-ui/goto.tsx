
import React from 'react'

import { Input } from '../ui/input'
import OutlineSelector from '@/components/outline-selector'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { useScenario } from '@/store'
import { Outline } from '@/types/scenario'

interface ButtonProps {
    properties: {
        "goto_settings": {
            "items": {
                "value": string,
                "type": string,
                "goto_id": string
            }[],
            "profile_key": string
        },
        "button_name": string,
        "button_key": string
    }
    onChange: (properties: any) => void
}

export default function Goto(props: ButtonProps) {
    const { properties } = props
    const {
        chapters,
    } = useScenario();

    const onValueChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        console.log('onChange', properties);
        props.onChange({
            ...properties,
            button_name: e.target.value,
            button_key: e.target.value
        })
    }
    const onNodeSelect = (index: number, node: Outline) => {
        console.log(index, node)
        props.onChange({
            ...properties,
            goto_settings: {
                ...properties.goto_settings,
                items: properties.goto_settings.items.map((item, i) => {
                    if (i === index) {
                        return {
                            ...item,
                            goto_id: node.id
                        }
                    }
                    return item
                })

            }
        })
    }
    console.log(properties)
    return (
        <div className='flex flex-col space-y-1'>
            <div className='flex flex-row items-center'>
                <div className='flex flex-row whitespace-nowrap'>
                    变量选择：
                </div>
                <Select >
                    <SelectTrigger className=" h-8 w-[120px]">
                        <SelectValue placeholder="选择变量" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="v1">变量一</SelectItem>
                        <SelectItem value="v2">变量二</SelectItem>
                    </SelectContent>
                </Select>
            </div>
            <div className='flex flex-row items-start py-2'>
                <div className='flex flex-row whitespace-nowrap'>
                    跳转位置：
                </div>
                <div className='flex flex-col space-y-1 '>
                    {
                        properties.goto_settings.items.map((item, index) => {
                            return (
                                <div className='flex flex-row items-center space-x-2' key={index}>
                                    <span className='w-40'>{item.value}</span>
                                    <span className='px-2'>跳转到</span>
                                    <span>
                                        <OutlineSelector value={item.goto_id} chapters={chapters} onSelect={onNodeSelect.bind(null, index)} />
                                    </span>
                                </div>
                            )
                        })
                    }
                </div>
            </div>

        </div>
    )
}
