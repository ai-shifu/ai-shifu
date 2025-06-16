import React from 'react'
import { useTranslation } from 'react-i18next';
import { memo } from 'react'
import _ from 'lodash'
interface InputViewProps {
    properties: {
        "input_name": string,
        "input_key": string,
        "input_placeholder": string
    }
}
const InputViewPropsEqual = (prevProps: InputViewProps, nextProps: InputViewProps) => {
    if (! _.isEqual(prevProps.properties, nextProps.properties)) {
        return false
    }
    if (! _.isEqual(prevProps.properties.input_name, nextProps.properties.input_name)) {
        return false
    }
    if (! _.isEqual(prevProps.properties.input_key, nextProps.properties.input_key)) {
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
