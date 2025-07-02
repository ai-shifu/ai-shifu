import React, { useState, useEffect, useCallback, memo } from 'react'
import { Input } from '../ui/input'
import { Button as UIButton } from '../ui/button'
import { useTranslation } from 'react-i18next';
import _ from 'lodash'
import { BlockDTO, ButtonDTO } from '@/types/shifu'
interface ButtonProps {
    id: string,
    properties: BlockDTO,
    onChange: (properties: BlockDTO) => void
    mode?: 'edit' | 'login' | 'payment'
    onChanged?: (changed: boolean) => void
}

const ButtonPropsEqual = (prevProps: ButtonProps, nextProps: ButtonProps) => {
    if (! _.isEqual(prevProps.properties, nextProps.properties)) {
        return false
    }
    if (!_.isEqual(prevProps.properties.properties.label, nextProps.properties.properties.label)) {
        return false
    }
    return true
}

export default memo(function Button(props: ButtonProps) {
    const { properties, mode = 'edit', onChanged } = props
    const buttonProperties = properties.properties as ButtonDTO
    const [tempValue, setTempValue] = useState(buttonProperties.label.lang['zh-CN'])
    const [changed, setChanged] = useState(false)
    const { t } = useTranslation();

    useEffect(() => {
        setChanged(false)
        setTempValue(buttonProperties.label.lang['zh-CN'])
    }, [buttonProperties.label.lang['zh-CN']])

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
                properties: {
                    ...buttonProperties,
                    label: {
                        ...buttonProperties.label,
                        lang: {
                            ...buttonProperties.label.lang,
                            'zh-CN': value
                        }
                    }
                }
            })
        }
    }, [changed, mode, onChanged, properties, props])

    const handleConfirm = useCallback(() => {
        props.onChange({
            ...properties,
            properties: {
                ...buttonProperties,
                label: {
                    ...buttonProperties.label,
                    lang: {
                        ...buttonProperties.label.lang,
                        'zh-CN': tempValue
                    }
                }
            }
        })
        if (!changed) {
            setChanged(true)
            onChanged?.(true)
        }
    }, [changed, onChanged, properties, props, tempValue])

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
},ButtonPropsEqual)
