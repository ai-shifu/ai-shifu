import React from 'react'
import { useTranslation } from 'react-i18next';
import { memo } from 'react'
interface InputViewProps {
    properties: {
        "input_name": string,
        "input_key": string,
        "input_placeholder": string
    }
}
const InputViewPropsEqual = (prevProps: InputViewProps, nextProps: InputViewProps) => {
    if (prevProps.properties.input_name !== nextProps.properties.input_name
        || prevProps.properties.input_key !== nextProps.properties.input_key
        || prevProps.properties.input_placeholder !== nextProps.properties.input_placeholder
    ) {
        return false
    }
    return true
}

export default memo(function InputView(props: InputViewProps) {
    const { properties } = props
    const { t } = useTranslation();
    return (
        <div className='flex flex-col space-y-2'>
            <div className='flex flex-row items-center space-x-1'>
                <span className='whitespace-nowrap'>{t('input.input-placeholder')}</span>
                <div className='px-3 py-2 bg-gray-50 rounded-md'>
                    {properties.input_placeholder}
                </div>
            </div>
            <div className='flex flex-row items-center space-x-1'>
                <span className='whitespace-nowrap'>{t('input.input-key')}</span>
                <div className='px-3 py-2 bg-gray-50 rounded-md'>
                    {properties.input_key}
                </div>
            </div>
            <div className='flex flex-row items-center space-x-1'>
                <span className='whitespace-nowrap'>{t('input.input-name')}</span>
                <div className='px-3 py-2 bg-gray-50 rounded-md'>
                    {properties.input_name}
                </div>
            </div>
        </div>
    )
},InputViewPropsEqual)
