import React from 'react'
import { Input } from '../ui/input'
import { useTranslation } from 'react-i18next';
import { memo } from 'react'
import _ from 'lodash'
import { UIBlockDTO ,InputDTO} from '@/types/shifu'
import i18n from '@/i18n'

const SingleInputPropsEqual = (prevProps: UIBlockDTO, nextProps: UIBlockDTO) => {
    const prevInputSettings = prevProps.data.properties as InputDTO
    const nextInputSettings = nextProps.data.properties as InputDTO
    if (! _.isEqual(prevProps.data, nextProps.data)) {
        return false
    }
    if (! _.isEqual(prevInputSettings.placeholder, nextInputSettings.placeholder)) {
        return false
    }
    if (! _.isEqual(prevInputSettings.prompt, nextInputSettings.prompt)) {
        return false
    }
    if (! _.isEqual(prevInputSettings.result_variable_bids, nextInputSettings.result_variable_bids)) {
        return false
    }
    if (! _.isEqual(prevInputSettings.llm, nextInputSettings.llm)) {
        return false
    }
    if (! _.isEqual(prevInputSettings.llm_temperature, nextInputSettings.llm_temperature)) {
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

export default memo(function SingleInput(props: UIBlockDTO) {
    const { data } = props
    const { t } = useTranslation();
    const inputSettings = data.properties as InputDTO
    const onValueChange = (e: React.ChangeEvent<HTMLInputElement>, field: string) => {
        if (field === 'prompt') {
            props.onPropertiesChange({
                ...data,
                properties: {
                    ...data.properties,
                    prompt: e.target.value,
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
                    {t('input.input-placeholder')}
                </span>
                <Input
                    className='h-8 w-40'
                    value={inputSettings.placeholder.lang[i18n.language]}
                    onChange={(e) => onValueChange(e, 'placeholder')}
                    placeholder={t('input.input-placeholder')}
                />
            </div>
            <div className='flex flex-row space-x-1 items-center'>
                <span className='flex flex-row whitespace-nowrap'>
                    {t('input.input-name')}
                </span>
                <Input
                    className='h-8 w-40'
                    value={inputSettings.prompt}
                    onChange={(e) => onValueChange(e, 'prompt')}
                    placeholder={t('input.input-name')}
                />
            </div>

        </div>
    )
},SingleInputPropsEqual)
