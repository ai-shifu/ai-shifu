import React, { useState, useEffect, useCallback } from 'react'
import { Input } from '../ui/input'
import { Button as UIButton } from '../ui/button'
import { useTranslation } from 'react-i18next';
interface ButtonProps {
    properties: {
        "button_name": string,
        "button_key": string,
    }
    onChange: (properties: any) => void
    mode?: 'edit' | 'login' | 'payment'
    onChanged?: (changed: boolean) => void
}

export default function Button(props: ButtonProps) {
    const { properties, mode = 'edit', onChanged } = props
    const [tempValue, setTempValue] = useState(properties.button_name)
    const [changed, setChanged] = useState(false)
    const { t } = useTranslation();

    useEffect(() => {
        setChanged(false)
        setTempValue(properties.button_name)
    }, [properties.button_name])

    const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const value = e.target.value
        setTempValue(value)
        if (!changed) {
            setChanged(true)
            onChanged?.(true)
        }
        if (mode === 'login' || mode === 'payment') {
            props.onChange({
                ...properties,
                button_name: value,
                button_key: value
            })
        }
    }, [changed, mode, onChanged, properties, props])

    const handleConfirm = useCallback(() => {
        props.onChange({
            ...properties,
            button_name: tempValue,
            button_key: tempValue
        })
        // 确认后保持 changed 为 true，因为内容确实已经改变
        if (!changed) {
            setChanged(true)
            onChanged?.(true)
        }
    }, [changed, onChanged, properties, props, tempValue])

    // Get the placeholder for input component based on the mode
    const getPlaceholder = () => {
        switch (mode) {
            case 'login':
                return t('button.placeholder-login')
            case 'payment':
                return t('button.placeholder-payment')
            case 'edit':
            default:
                return t('button.placeholder-edit')
        }
    }

    return (
        <div className='flex flex-col space-y-2'>
            <div className='flex flex-row space-x-1 items-center'>
                <span className='flex flex-row whitespace-nowrap w-[70px] shrink-0'>
                    {t('button.button-name')}
                </span>
                <Input
                    className='h-8 w-40'
                    value={tempValue}
                    onChange={handleInputChange}
                    placeholder={getPlaceholder()}
                />
            </div>

            {mode === 'edit' && (
                <div className='flex flex-row space-x-1 items-center'>
                    <span className='flex flex-row whitespace-nowrap w-[70px] shrink-0'>
                    </span>
                    <UIButton
                        className='h-8 w-20'
                        onClick={handleConfirm}
                    >
                        {t('button.complete')}
                    </UIButton>
                </div>
            )}
        </div>
    )
}
