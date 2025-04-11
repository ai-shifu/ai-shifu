
import React from 'react'
import { Input } from '../ui/input'
import { Textarea } from '../ui/textarea'
import InputNumber from '@/components/input-number'
import ModelList from '@/components/model-list'

interface ButtonProps {
    properties: {
        "prompt": {
            "properties": {
                "prompt": string,
                "profiles": string[],
                "model": string,
                "temprature": string,
                "other_conf": string,
            },
            "type": string
        },
        "input_name": string,
        "input_key": string,
        "input_placeholder": string
    }
    onChange: (properties: any) => void
}

export default function TextInput(props: ButtonProps) {
    const { properties } = props;

    const onValueChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        props.onChange({
            ...properties,
            prompt: {
                ...properties.prompt,
                properties:
                {
                    ...properties.prompt.properties,
                    prompt: e.target.value
                }
            }
        })
    }
    const onModelChange = (value: string) => {
        props.onChange({ ...properties, prompt: { ...properties.prompt, properties: { ...properties.prompt.properties, model: value } } })
    }
    const onTemperatureChange = (value: number) => {
        console.log({ ...properties, prompt: { ...properties.prompt, temprature: value } })
        props.onChange({ ...properties, prompt: { ...properties.prompt, properties: { ...properties.prompt.properties, temprature: value } } })
    }
    const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        console.log('onChange', properties);
        props.onChange({
            ...properties,
            input_key: e.target.value,
        })
    }
    const onInputPlaceholderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        console.log('onChange', properties);
        props.onChange({
            ...properties,
            input_name: e.target.value,
            input_placeholder: e.target.value
        })
    }
    return (
        <div className='flex flex-col space-y-2 w-full'>
            <div className='flex flex-row items-center space-x-1'>
                <label htmlFor="" className=' whitespace-nowrap w-[70px] shrink-0'>
                    输入提示：
                </label>
                <Input value={properties.input_name} onChange={onInputPlaceholderChange} className="w-full" ></Input>
            </div>
            <div className='flex flex-row items-center space-x-1'>
                <label htmlFor="" className=' whitespace-nowrap w-[70px] shrink-0'>
                    变量名：
                </label>
                <Input value={properties.input_key} onChange={onInputChange} className="w-full" ></Input>
            </div>
            <div className='flex flex-row items-center space-x-1'>
                <label htmlFor="" className=' whitespace-nowrap w-[70px] shrink-0'>
                    提示词：
                </label>
                <Textarea value={properties.prompt.properties.prompt} onChange={onValueChange} className="w-full"></Textarea>
            </div>
            <div className='flex flex-row items-center space-x-1'>
                <label htmlFor="" className=' whitespace-nowrap w-[70px] shrink-0'>
                    指定模型：
                </label>
                <ModelList value={properties.prompt.properties.model} className=" h-8 w-[120px]" onChange={onModelChange} />
            </div>
            <div className='flex flex-row items-center space-x-1 w-[275px]'>
                <label htmlFor="" className=' whitespace-nowrap w-[70px] shrink-0'>
                    设定温度：
                </label>
                <InputNumber min={0} max={1} step={0.1}
                    value={Number(properties.prompt?.properties?.temprature)}
                    onChange={onTemperatureChange} className="w-full"
                ></InputNumber>
            </div>
        </div>
    )
}
