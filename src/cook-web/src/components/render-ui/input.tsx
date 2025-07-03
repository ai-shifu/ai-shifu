import React from 'react'
import { Input } from '../ui/input'
import { useTranslation } from 'react-i18next';
import { memo } from 'react'
import _ from 'lodash'
import { BlockDTO ,InputDTO} from '@/types/shifu'
interface SingleInputProps {
    properties: BlockDTO
    onChange: (properties: BlockDTO) => void
}

const SingleInputPropsEqual = (prevProps: SingleInputProps, nextProps: SingleInputProps) => {
    const prevInputSettings = prevProps.properties.properties as InputDTO
    const nextInputSettings = nextProps.properties.properties as InputDTO
    if (! _.isEqual(prevProps.properties, nextProps.properties)) {
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
    if (! _.isEqual(prevProps.properties.variable_bids, nextProps.properties.variable_bids)) {
        return false
    }
    if (! _.isEqual(prevProps.properties.resource_bids, nextProps.properties.resource_bids)) {
        return false
    }
    return true
}

export default memo(function SingleInput(props: SingleInputProps) {
    const { properties } = props
    const { t } = useTranslation();
    const onValueChange = (e: React.ChangeEvent<HTMLInputElement>, field: string) => {
        if (field === 'prompt') {
            props.onChange({
                ...properties,
                properties: {
                    ...properties.properties,
                    prompt: e.target.value,
                }
            });
            return;
        }
        props.onChange({
            ...properties,
            properties: {
                ...properties.properties,
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
                    value={properties.properties.placeholder.lang[i18n.language]}
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
                    value={properties.properties.prompt}
                    onChange={(e) => onValueChange(e, 'prompt')}
                    placeholder={t('input.input-name')}
                // type="tel"
                // placeholder={properties.input_placeholder}
                />
            </div>

        </div>
    )
},SingleInputPropsEqual)
