import React from 'react'
import { useTranslation } from 'react-i18next';
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

/**
 * Displays an option's name and a list of associated buttons in a styled, read-only view.
 *
 * Renders the option name with a translated label and displays each button as a disabled element.
 */
export default function OptionView(props: OptionViewProps) {
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
}
