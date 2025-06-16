import React from 'react'
import { useTranslation } from 'react-i18next';
import { memo } from 'react'
import _ from 'lodash'
interface GotoViewProps {
    properties: {
        "goto_settings": {
            "items": Array<{
                "value": string,
                "type": string,
                "goto_id": string
            }>,
            "profile_key": string
        },
        "button_name": string,
        "button_key": string
    }
}
const GotoViewPropsEqual = (prevProps: GotoViewProps, nextProps: GotoViewProps) => {
    if (! _.isEqual(prevProps.properties, nextProps.properties)) {
        return false
    }
    for (let i = 0; i < prevProps.properties.goto_settings.items.length; i++) {
        if (!_.isEqual(prevProps.properties.goto_settings.items[i], nextProps.properties.goto_settings.items[i])) {
            return false
        }
    }
    if (! _.isEqual(prevProps.properties.goto_settings.profile_key, nextProps.properties.goto_settings.profile_key)) {
        return false
    }
    if (! _.isEqual(prevProps.properties.button_name, nextProps.properties.button_name)) {
        return false
    }
    return true
}

export default memo(function GotoView(props: GotoViewProps) {
    const { properties } = props
    const { t } = useTranslation();
    return (
        <div className='flex flex-col space-y-2'>
            <div className='flex flex-row items-center space-x-1'>
                <span className='whitespace-nowrap'>{t('goto.goto-settings')}</span>
                <div className='flex flex-col space-y-1 bg-gray-50 rounded-md p-2'>
                    {properties.goto_settings.items.map((item, index) => (
                        <div key={index} className='px-3 py-2 bg-gray-100 rounded-md'>
                            {item.value}
                        </div>
                    ))}
                </div>
            </div>
            <div className='flex flex-row items-center space-x-1'>
                <span className='whitespace-nowrap'>{t('goto.button-name')}</span>
                <button
                    className='px-4 py-2 bg-gray-100 text-gray-700 rounded-md cursor-default'
                    disabled
                >
                    {properties.button_name}
                </button>
            </div>
        </div>
    )
},GotoViewPropsEqual)
