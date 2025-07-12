import React from 'react'
import { Input } from '../ui/input'
import { useTranslation } from 'react-i18next';
import { memo } from 'react'
import _ from 'lodash'
import { UIBlockDTO, GeneralInputDTO } from '@/types/shifu'
import i18n from '@/i18n'

const GeneralInputPropsEqual = (prevProps: UIBlockDTO, nextProps: UIBlockDTO) => {
    const prevGeneralInputSettings = prevProps.data.properties as GeneralInputDTO
    const nextGeneralInputSettings = nextProps.data.properties as GeneralInputDTO
    if (! _.isEqual(prevProps.data, nextProps.data)) {
        return false
    }
    if (! _.isEqual(prevGeneralInputSettings.input_placeholder, nextGeneralInputSettings.input_placeholder)) {
        return false
    }
    if (! _.isEqual(prevProps.data.variable_bids, nextProps.data.variable_bids)) {
        return false
    }
    if (! _.isEqual(prevProps.data.resource_bids, nextProps.data.resource_bids)) {
        return false
    }
    return true
}

export default memo(function GeneralInput(props: UIBlockDTO) {
    const { data } = props
    const { t } = useTranslation();
    const generalInputSettings = data.properties as GeneralInputDTO

    const onValueChange = (e: React.ChangeEvent<HTMLInputElement>, field: string) => {
        if (field === 'input_placeholder') {
            props.onPropertiesChange({
                ...data,
                properties: {
                    ...data.properties,
                    input_placeholder: {
                        lang: {
                            ...generalInputSettings.input_placeholder.lang,
                            [i18n.language]: e.target.value,
                        }
                    }
                }
            });
            return;
        }
        props.onPropertiesChange({
            ...data,
            properties: {
                ...data.properties,
                [field]: e.target.value,
            }
        })
    }

    return (
        <div className='flex flex-col space-y-2'>
            <div className='flex flex-row space-x-1 items-center'>
                <span className='flex flex-row whitespace-nowrap'>
                    输入提示词
                </span>
                <Input
                    className='h-8 w-40'
                    value={generalInputSettings.input_placeholder.lang[i18n.language] || ''}
                    onChange={(e) => onValueChange(e, 'input_placeholder')}
                    placeholder='请输入提示词'
                />
            </div>
        </div>
    )
}, GeneralInputPropsEqual)
