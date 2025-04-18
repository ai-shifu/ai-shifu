import React from 'react'

interface TextInputViewProps {
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
}

export default function TextInputView(props: TextInputViewProps) {
    const { properties } = props
    return (
        <div className='flex flex-col space-y-2 w-full'>
            <div className='flex flex-row items-center space-x-1'>
                <label className='whitespace-nowrap w-[70px] shrink-0'>
                    输入提示：
                </label>
                <div className='px-3 py-2 bg-gray-50 rounded-md w-full'>
                    {properties.input_name}
                </div>
            </div>
            <div className='flex flex-row items-center space-x-1'>
                <label className='whitespace-nowrap w-[70px] shrink-0'>
                    变量名：
                </label>
                <div className='px-3 py-2 bg-gray-50 rounded-md w-full'>
                    {properties.input_key}
                </div>
            </div>
            <div className='flex flex-row items-center space-x-1'>
                <label className='whitespace-nowrap w-[70px] shrink-0'>
                    提示词：
                </label>
                <div className='px-3 py-2 bg-gray-50 rounded-md w-full min-h-[80px] whitespace-pre-wrap'>
                    {properties.prompt.properties.prompt}
                </div>
            </div>
            <div className='flex flex-row items-center space-x-1'>
                <label className='whitespace-nowrap w-[70px] shrink-0'>
                    指定模型：
                </label>
                <div className='px-3 py-2 bg-gray-50 rounded-md w-[200px]'>
                    {properties.prompt.properties.model}
                </div>
            </div>
            <div className='flex flex-row items-center space-x-1 w-[275px]'>
                <label className='whitespace-nowrap w-[70px] shrink-0'>
                    设定温度：
                </label>
                <div className='px-3 py-2 bg-gray-50 rounded-md w-full'>
                    {properties.prompt.properties.temprature}
                </div>
            </div>
        </div>
    )
}
