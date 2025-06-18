import React from 'react'
import { useTranslation } from 'react-i18next';
import { memo } from 'react'
import _ from 'lodash'
interface TextInputViewProps {
    properties: {
        "prompt": {
            "properties": {
                "prompt": string,
                "profiles": string[],
                "model": string,
                "temperature": string,
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
    if (_.isEqual(prevProps.properties, nextProps.properties)) {
        return false
    }
    if (!_.isEqual(prevProps.properties.prompt.properties.prompt, nextProps.properties.prompt.properties.prompt)) {
        return false
    }
    if (!_.isEqual(prevProps.properties.prompt.properties.temperature, nextProps.properties.prompt.properties.temperature)) {
        return false
    }
    if (!_.isEqual(prevProps.properties.prompt.properties.profiles, nextProps.properties.prompt.properties.profiles)) {
        return false
    }
    if (!_.isEqual(prevProps.properties.prompt.properties.profiles, nextProps.properties.prompt.properties.profiles)) {
        return false
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
                    {properties.prompt.properties.temperature}
                </div>
            </div>
        </div>
    )
},TextInputViewPropsEqual)
