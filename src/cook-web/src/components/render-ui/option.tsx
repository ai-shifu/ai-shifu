
import React from 'react'
import { Input } from '../ui/input'
import { Plus, Trash } from 'lucide-react'
import { Button } from '../ui/button'


interface ButtonProps {
    properties: {
        "option_name": string,
        "option_key": string,
        "profile_key": string,
        "buttons": {
            "properties": {
                "button_name": string,
                "button_key": string,
            },
            "type": string
        }[]
    }
    onChange: (properties: any) => void
}

export default function Option(props: ButtonProps) {
    const { properties, onChange } = props;
    const { option_name, option_key, profile_key, buttons } = properties;
    const onValueChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        console.log('onChange', properties);
        props.onChange({
            ...properties,
            option_name: e.target.value,
            option_key: e.target.value
        })
    }
    const onButtonTextChange = (index: number, e: React.ChangeEvent<HTMLInputElement>) => {
        // console.log('onChange', properties);
        props.onChange({
            ...properties,
            buttons: buttons.map((button: any, i: number) => {
                if (i === index) {
                    return {
                        ...button,
                        properties: {
                            ...button.properties,
                            button_name: e.target.value,
                            button_key: e.target.value
                        }
                    }
                }
                return button;
            })
        })
    }
    const onAdd = () => {
        props.onChange({
            ...properties,
            buttons: [
                ...buttons,
                {
                    "properties": {
                        "button_name": "",
                        "button_key": ""
                    },
                    "type": "button"
                }
            ]
        })
    }
    const onDelete = (index: number) => {
        props.onChange({
            ...properties,
            buttons: buttons.filter((_: any, i: number) => i !== index)
        })
    }
    return (
        <div className='flex flex-col space-y-1'>
            <div className='flex flex-row items-center'>
                <span className='flex flex-row items-center whitespace-nowrap'>
                    选项名称：
                </span>
                <Input className='h-8' value={option_name} onChange={onValueChange}></Input>
            </div>
            <div className='grid grid-cols-4 gap-1'>
                {
                    buttons.map((button: any, index: number) => {
                        return (
                            <div key={index} className='flex flex-row items-center space-x-1'>
                                <span className='flex flex-row items-center whitespace-nowrap'>
                                    按钮 {index + 1} 文案：
                                </span>
                                <Input value={button.properties.button_name} onChange={onButtonTextChange.bind(null, index)}></Input>
                                <Button className='h-8 w-8' variant="ghost" onClick={onDelete.bind(null, index)} >
                                    <Trash />
                                </Button>
                            </div>
                        )
                    })
                }
                <Button className='h-8 w-8' variant="ghost" onClick={onAdd}>
                    <Plus />
                </Button>
            </div>

        </div >
    )
}
