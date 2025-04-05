import React from 'react'
import { Input } from '../ui/input'

interface ButtonProps {
    properties: {
        "input_name": string,
        "input_key": string,
        "input_placeholder": string,
    }
    onChange: (properties: any) => void
}

export default function SingleInput(props: ButtonProps) {
    const { properties } = props

    const onValueChange = (e: React.ChangeEvent<HTMLInputElement>, field: string) => {
        console.log('onChange', properties);
        if (field === 'input_name') {
            props.onChange({
                ...properties,
                input_name: e.target.value,
                input_key: e.target.value,
            });
            return;
        }
        props.onChange({
            ...properties,
            [field]: e.target.value,
        })
    }

    return (
        <div className='flex flex-col space-y-2'>
            <div className='flex flex-row space-x-1 items-center'>
                <span className='flex flex-row whitespace-nowrap'>
                    输入框提示：
                </span>
                <Input
                    className='h-8 w-40'
                    value={properties.input_placeholder}
                    onChange={(e) => onValueChange(e, 'input_placeholder')}
                    placeholder="请输入提示文本"
                />
            </div>
            <div className='flex flex-row space-x-1 items-center'>
                <span className='flex flex-row whitespace-nowrap'>
                    输入框名称：
                </span>
                <Input
                    className='h-8 w-40'
                    value={properties.input_name}
                    onChange={(e) => onValueChange(e, 'input_name')}
                    type="tel"
                    placeholder={properties.input_placeholder}
                />
            </div>

        </div>
    )
}
