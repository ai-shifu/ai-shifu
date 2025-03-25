
import React from 'react'
import { Input } from '../ui/input'
import { Textarea } from '../ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

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
        console.log('onChange', properties);
        props.onChange({ ...properties, prompt: { ...properties.prompt, properties: { ...properties.prompt.properties, prompt: e.target.value } } })

    }
    const onModelChange = (value: string) => {
        console.log('onChange', value);
        props.onChange({ ...properties, prompt: { ...properties.prompt, model: value } })
    }
    const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        console.log('onChange', properties);
        props.onChange({
            ...properties,
            input_name: e.target.value,
            input_key: e.target.value,
            input_placeholder: e.target.value
        })
    }
    return (
        <div className='flex flex-col space-y-1'>
            <div className='py-2'>
                <div className='py-2 flex flex-row items-center'>
                    <span>
                        检查内容
                    </span>
                    <span className='px-4 text-gray-300'>
                        |
                    </span>
                    <span>
                        指定模型：
                    </span>
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
                <Textarea value={properties.prompt.properties.prompt} onChange={onValueChange} className="w-full"></Textarea>
            </div>
            <div>
                定义变量
            </div>
            <Input value={properties.input_name} onChange={onInputChange} className="w-full" ></Input>
        </div>
    )
}
