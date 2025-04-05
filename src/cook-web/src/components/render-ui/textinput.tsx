
import React from 'react'
import { Input } from '../ui/input'
import { Textarea } from '../ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import InputNumber from '@/components/input-number'
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
    const { properties } = props


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
        props.onChange({
            ...properties,

            input_name: e.target.value,
            input_key: e.target.value,
        })
    }
    const onInputPlaceholderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        console.log('onChange', properties);
        props.onChange({
            ...properties,
            input_placeholder: e.target.value
        })
    }
    return (
        <div className='flex flex-col space-y-2 w-full'>
            <div className='flex flex-row items-center space-x-1'>
                <label htmlFor="" className=' whitespace-nowrap w-[70px] shrink-0'>
                    输入提示：
                </label>
                <Input value={properties.input_placeholder} onChange={onInputPlaceholderChange} className="w-full" ></Input>
            </div>
            <div className='flex flex-row items-center space-x-1'>
                <label htmlFor="" className=' whitespace-nowrap w-[70px] shrink-0'>
                    变量名：
                </label>
                <Input value={properties.input_name} onChange={onInputChange} className="w-full" ></Input>
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
                <Select onValueChange={onModelChange}>
                    <SelectTrigger className=" h-8 w-[120px]">
                        <SelectValue placeholder="选择模型" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="gpt-4">GDP-4</SelectItem>
                        <SelectItem value="gpt-4o">GDP-4o</SelectItem>
                        <SelectItem value="deepseek">DeepSeek</SelectItem>
                    </SelectContent>
                </Select>
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
