
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
    const { properties } = props;
    const { option_name, buttons } = properties;
    const onValueChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        console.log('onChange', properties);
        props.onChange({
            ...properties,
            option_name: e.target.value,
            option_key: e.target.value
        })
    }
    const onButtonValueChange = (index: number, e: React.ChangeEvent<HTMLInputElement>) => {
        // console.log('onChange', properties);
        props.onChange({
            ...properties,
            buttons: buttons.map((button: any, i: number) => {
                if (i === index) {
                    return {
                        ...button,
                        properties: {
                            ...button.properties,
                            button_key: e.target.value
                        }
                    }
                }
                return button;
            })
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
                        }
                    }
                }
                return button;
            })
        })
    }
    const onAdd = (index: number) => {
        // console.log('onChange', properties);
        const newButton = {
            "properties": {
                "button_name": "",
                "button_key": ""
            },
            "type": "button"
        }
        props.onChange({
            ...properties,
            buttons: [
                ...buttons.slice(0, index + 1),
                newButton,
                ...buttons.slice(index + 1)
            ]
        })
        // props.onChange({
        //     ...properties,
        //     buttons: [
        //         ...buttons,
        //         {
        //             "properties": {
        //                 "button_name": "",
        //                 "button_key": ""
        //             },
        //             "type": "button"
        //         }
        //     ]
        // })
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
                <span className='flex flex-row items-center whitespace-nowrap  w-[50px] shrink-0'>
                    变量：
                </span>
                <Input className='h-8 w-[400px]' placeholder='请输入' value={option_name} onChange={onValueChange}></Input>
            </div>
            <div className='flex flex-col space-y-2'>
                {
                    buttons.map((button: any, index: number) => {
                        return (
                            <div key={index} className='flex flex-row items-center'>
                                <span className='flex flex-row items-center whitespace-nowrap  w-[50px] shrink-0'>
                                    值：
                                </span>
                                <Input value={button.properties.button_key} className='w-40' onChange={onButtonValueChange.bind(null, index)}></Input>
                                <span className='flex flex-row items-center whitespace-nowrap  w-[50px] ml-4'>
                                    标题：
                                </span>
                                <Input value={button.properties.button_name} className='w-40 ml-4' onChange={onButtonTextChange.bind(null, index)}></Input>
                                <Button className='h-8 w-8' variant="ghost" onClick={onAdd.bind(null, index)} >
                                    <Plus />
                                </Button>
                                <Button className='h-8 w-8' variant="ghost" onClick={onDelete.bind(null, index)} >
                                    <Trash />
                                </Button>
                            </div>
                        )
                    })
                }

            </div>

        </div >
    )
}
