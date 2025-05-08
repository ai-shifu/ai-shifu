import React from 'react'
import { useTranslation } from 'react-i18next';
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

/**
 * Displays a list of "goto" settings and a disabled button with localized labels.
 *
 * Renders a vertical layout showing each item from the provided goto settings and a button name, using translations for section labels.
 *
 * @param props - Contains the properties for rendering goto settings and button name.
 */
export default function GotoView(props: GotoViewProps) {
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
}
