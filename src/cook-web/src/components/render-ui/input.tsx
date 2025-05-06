import React from 'react'
import { Input } from '../ui/input'
import { useTranslation } from 'react-i18next';
interface ButtonProps {
    properties: {
        "input_name": string,
        "input_key": string,
        "input_placeholder": string,
    }
    onChange: (properties: any) => void
}

/**
 * Renders two labeled input fields for name and placeholder, updating their values via a callback.
 *
 * When the name field is changed, both the name and key properties are updated to match the new value.
 *
 * @param props - Contains input field properties and an `onChange` callback to handle updates.
 *
 * @remark
 * Labels and placeholders are localized using the current translation context.
 */
export default function SingleInput(props: ButtonProps) {
    const { properties } = props
    const { t } = useTranslation();
    const onValueChange = (e: React.ChangeEvent<HTMLInputElement>, field: string) => {
        console.log('onChange', properties);
        if (field === 'input_name') {
            props.onChange({
                ...properties,
                input_name: e.target.value,
                input_key: e.target.value,
            });
            return;
        }
        props.onChange({
            ...properties,
            [field]: e.target.value,
        })
    }

    return (
        <div className='flex flex-col space-y-2'>
            <div className='flex flex-row space-x-1 items-center'>
                <span className='flex flex-row whitespace-nowrap'>
                    {t('input.input-placeholder')}
                </span>
                <Input
                    className='h-8 w-40'
                    value={properties.input_placeholder}
                    onChange={(e) => onValueChange(e, 'input_placeholder')}
                    placeholder={t('input.input-placeholder')}
                />
            </div>
            <div className='flex flex-row space-x-1 items-center'>
                <span className='flex flex-row whitespace-nowrap'>
                    {t('input.input-name')}
                </span>
                <Input
                    className='h-8 w-40'
                    value={properties.input_name}
                    onChange={(e) => onValueChange(e, 'input_name')}
                    placeholder={t('input.input-name')}
                // type="tel"
                // placeholder={properties.input_placeholder}
                />
            </div>

        </div>
    )
}
