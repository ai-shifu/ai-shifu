
import React from 'react'
import { Input } from '../ui/input'

interface ButtonProps {
    properties: {
        "button_name": string,
        "button_key": string,
    }
    onChange: (properties: any) => void
}

export default function Button(props: ButtonProps) {
    const { properties } = props

    const onValueChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        console.log('onChange', properties);
        props.onChange({
            ...properties,
            button_name: e.target.value,
            button_key: e.target.value
        })
    }
    return (
        <div className='flex flex-row space-x-1 items-center'>
            <span className='flex flex-row whitespace-nowrap'>
                按钮文案：
            </span>
            <Input className='h-8 w-40' value={properties.button_name} onChange={onValueChange}></Input>
        </div>
    )
}
