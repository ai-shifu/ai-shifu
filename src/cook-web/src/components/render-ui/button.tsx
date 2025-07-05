import React, { useState, useEffect, useCallback, memo } from 'react'
import { Input } from '../ui/input'
import { Button as UIButton } from '../ui/button'
import { useTranslation } from 'react-i18next';
import _ from 'lodash'
import { UIBlockDTO, ButtonDTO } from '@/types/shifu'

const ButtonPropsEqual = (prevProps: UIBlockDTO, nextProps: UIBlockDTO) => {

    if (!_.isEqual(prevProps.data, nextProps.data)) {
        return false
    }
    if (!_.isEqual(prevProps.data.properties, nextProps.data.properties)) {
        return false
    }
    return true
}

export default memo(function Button(props: UIBlockDTO) {
    const { data, onChanged, onPropertiesChange, isEdit } = props
    const type = data.type
    const buttonProperties = data.properties as ButtonDTO
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
        onPropertiesChange({
            ...data,
            properties: {
                ...data.properties,
                label: {
                    ...buttonProperties.label,
                    lang: {
                        ...buttonProperties.label.lang,
                        'zh-CN': value,
                        'en-US': value
                    }
                }
            }
        })
    }, [changed, onChanged, data, onPropertiesChange, tempValue])

    const handleConfirm = useCallback(() => {
        onPropertiesChange({
            ...data,
            properties: {
                ...data.properties,
                label: {
                    ...buttonProperties.label,
                    lang: {
                        ...buttonProperties.label.lang,
                        'zh-CN': tempValue,
                        'en-US': tempValue
                    }
                }
            }
        })
        if (!changed) {
            setChanged(true)
            onChanged?.(true)
        }
    }, [changed, onChanged, data, onPropertiesChange, tempValue])

    const getPlaceholder = () => {
        switch (type) {
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

            {isEdit && (
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
}, ButtonPropsEqual)
