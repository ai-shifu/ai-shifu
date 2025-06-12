import React from 'react'
import { useTranslation } from 'react-i18next';
import { memo } from 'react'
import _ from 'lodash'
interface OptionViewProps {
    properties: {
        "option_name": string,
        "option_key": string,
        "profile_key": string,
        "buttons": Array<{
            "properties": {
                "button_name": string,
                "button_key": string
            },
            "type": string
        }>
    }
}
const OptionViewPropsEqual = (prevProps: OptionViewProps, nextProps: OptionViewProps) => {
    if (! _.isEqual(prevProps.properties, nextProps.properties)) {
        return false
    }
    if (! _.isEqual(prevProps.properties.option_name, nextProps.properties.option_name)) {
        return false
    }
    if (! _.isEqual(prevProps.properties.option_key, nextProps.properties.option_key)) {
        return false
    }
    if (! _.isEqual(prevProps.properties.profile_key, nextProps.properties.profile_key)) {
        return false
    }
    for (let i = 0; i < prevProps.properties.buttons.length; i++) {
        if (prevProps.properties.buttons[i].properties.button_name !== nextProps.properties.buttons[i].properties.button_name
            || prevProps.properties.buttons[i].properties.button_key !== nextProps.properties.buttons[i].properties.button_key
        ) {
            return false
        }
    }
    return true
}

export default memo(function OptionView(props: OptionViewProps) {
    const { properties } = props
    const { t } = useTranslation();
    return (
        <div className='flex flex-col space-y-2'>
            <div className='flex flex-row items-center space-x-1'>
                <span className='whitespace-nowrap'>{t('option.option-name')}</span>
                <div className='px-3 py-2 bg-gray-50 rounded-md'>
                    {properties.option_name}
                </div>
            </div>
            <div className='flex flex-row flex-wrap gap-2'>
                {properties.buttons.map((button, index) => (
                    <button
                        key={index}
                        className='px-4 py-2 bg-gray-100 text-gray-700 rounded-md cursor-default'
                        disabled
                    >
                        {button.properties.button_name}
                    </button>
                ))}
            </div>
        </div>
    )
},OptionViewPropsEqual)
