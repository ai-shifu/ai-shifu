import React from 'react'
import { useTranslation } from 'react-i18next';
import { memo } from 'react'
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
const TextInputViewPropsEqual = (prevProps: TextInputViewProps, nextProps: TextInputViewProps) => {
    if (prevProps.properties.input_name !== nextProps.properties.input_name
        || prevProps.properties.input_key !== nextProps.properties.input_key
        || prevProps.properties.input_placeholder !== nextProps.properties.input_placeholder
    ) {
        return false
    }
    if (prevProps.properties.prompt.properties.prompt !== nextProps.properties.prompt.properties.prompt
        || prevProps.properties.prompt.properties.model !== nextProps.properties.prompt.properties.model
    ) {
        return false
    }
    if (prevProps.properties.prompt.properties.temprature !== nextProps.properties.prompt.properties.temprature) {
        return false
    }
    if (prevProps.properties.prompt.properties.profiles.length !== nextProps.properties.prompt.properties.profiles.length) {
        return false
    }
    for (let i = 0; i < prevProps.properties.prompt.properties.profiles.length; i++) {
        if (!nextProps.properties.prompt.properties.profiles.includes(prevProps.properties.prompt.properties.profiles[i])) {
            return false
        }
    }
    return true
}

export default memo(function TextInputView(props: TextInputViewProps) {
    const { properties } = props
    const { t } = useTranslation();
    return (
        <div className='flex flex-col space-y-2 w-full'>
            <div className='flex flex-row items-center space-x-1'>
                <label className='whitespace-nowrap w-[70px] shrink-0'>
                    {t('textinput.input-placeholder')}
                </label>
                <div className='px-3 py-2 bg-gray-50 rounded-md w-full'>
                    {properties.input_name}
                </div>
            </div>
            <div className='flex flex-row items-center space-x-1'>
                <label className='whitespace-nowrap w-[70px] shrink-0'>
                    {t('textinput.input-key')}
                </label>
                <div className='px-3 py-2 bg-gray-50 rounded-md w-full'>
                    {properties.input_key}
                </div>
            </div>
            <div className='flex flex-row items-center space-x-1'>
                <label className='whitespace-nowrap w-[70px] shrink-0'>
                    {t('textinput.prompt')}
                </label>
                <div className='px-3 py-2 bg-gray-50 rounded-md w-full min-h-[80px] whitespace-pre-wrap'>
                    {properties.prompt.properties.prompt}
                </div>
            </div>
            <div className='flex flex-row items-center space-x-1'>
                <label className='whitespace-nowrap w-[70px] shrink-0'>
                    {t('textinput.model')}
                </label>
                <div className='px-3 py-2 bg-gray-50 rounded-md w-[200px]'>
                    {properties.prompt.properties.model}
                </div>
            </div>
            <div className='flex flex-row items-center space-x-1 w-[275px]'>
                <label className='whitespace-nowrap w-[70px] shrink-0'>
                    {t('textinput.temperature')}
                </label>
                <div className='px-3 py-2 bg-gray-50 rounded-md w-full'>
                    {properties.prompt.properties.temprature}
                </div>
            </div>
        </div>
    )
},TextInputViewPropsEqual)
