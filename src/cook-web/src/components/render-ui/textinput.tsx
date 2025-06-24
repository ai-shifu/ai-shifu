import React, { useState } from 'react'
import { Input } from '../ui/input'
import { Editor } from '@/components/cm-editor'
import InputNumber from '@/components/input-number'
import ModelList from '@/components/model-list'
import { Button } from '../ui/button'
import { useTranslation } from 'react-i18next';
import { memo } from 'react'
import _ from 'lodash'
interface TextInputProps {
    properties: {
        "prompt": {
            "properties": {
                "prompt": string,
                "profiles": string[],
                "model": string,
                "temperature": string,
                "other_conf": string,
            },
            "type": string
        },
        "input_name": string,
        "input_key": string,
        "input_placeholder": string
    }
    onChange: (properties: any) => void
    onChanged?: (changed: boolean) => void
}

const TextInputPropsEqual = (prevProps: TextInputProps, nextProps: TextInputProps) => {
    if (! _.isEqual(prevProps.properties, nextProps.properties)) {
        return false
    }
    if (!_.isEqual(prevProps.properties.prompt.properties.temperature, nextProps.properties.prompt.properties.temperature)) {
        return false
    }
    if (!_.isEqual(prevProps.properties.prompt.properties.profiles, nextProps.properties.prompt.properties.profiles)) {
        return false
    }
    if (!_.isEqual(prevProps.properties.prompt.properties.prompt, nextProps.properties.prompt.properties.prompt)) {
        return false
    }
    for (let i = 0; i < prevProps.properties.prompt.properties.profiles.length; i++) {
        if (!nextProps.properties.prompt.properties.profiles.includes(prevProps.properties.prompt.properties.profiles[i])) {
            return false
        }
    }
    return true
}

export default memo(function TextInput(props: TextInputProps) {
    const { properties, onChanged } = props;
    const [tempProperties, setTempProperties] = useState(properties);
    const [changed, setChanged] = useState(false);
    const { t } = useTranslation();
    const onValueChange = (value: string) => {
        if (!changed) {
            setChanged(true);
            onChanged?.(true);

        }
        setTempProperties({
            ...tempProperties,
            prompt: {
                ...tempProperties.prompt,
                properties: {
                    ...tempProperties.prompt.properties,
                    prompt: value
                }
            }
        });
    }

    const onModelChange = (value: string) => {
        setTempProperties({
            ...tempProperties,
            prompt: {
                ...tempProperties.prompt,
                properties: {
                    ...tempProperties.prompt.properties,
                    model: value
                }
            }
        });
    }

    const onTemperatureChange = (value: number) => {
        setTempProperties({
            ...tempProperties,
            prompt: {
                ...tempProperties.prompt,
                properties: {
                    ...tempProperties.prompt.properties,
                    temperature: value.toString()
                }
            }
        });
    }

    const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setTempProperties({
            ...tempProperties,
            input_key: e.target.value,
        });
    }

    const onInputPlaceholderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setTempProperties({
            ...tempProperties,
            input_name: e.target.value,
            input_placeholder: e.target.value
        });
    }

    const handleConfirm = () => {
        props.onChange(tempProperties);
    }

    return (
        <div className='flex flex-col space-y-2 w-full'>
            <div className='flex flex-row items-center space-x-1'>
                <label htmlFor="" className='whitespace-nowrap w-[70px] shrink-0'>
                    {t('textinput.input-placeholder')}
                </label>
                <Input value={tempProperties.input_name} onChange={onInputPlaceholderChange} className="w-full" ></Input>
            </div>
            <div className='flex flex-row items-center space-x-1'>
                <label htmlFor="" className='whitespace-nowrap w-[70px] shrink-0'>
                    {t('textinput.input-name')}
                </label>
                <Input value={tempProperties.input_key} onChange={onInputChange} className="w-full" ></Input>
            </div>
            <div className='flex flex-row space-x-1'>
                <label htmlFor="" className='whitespace-nowrap w-[70px] shrink-0'>
                    {t('textinput.prompt')}
                </label>
                <div className="w-full rounded-md border bg-background px-1 py-1">
                    <div style={{ minHeight: '72px', maxHeight: '480px', overflowY: 'auto' }}>
                        <Editor
                            content={tempProperties.prompt.properties.prompt}
                            onChange={onValueChange}
                            isEdit={true}
                            profiles={tempProperties.prompt.properties.profiles}
                        />
                    </div>
                </div>
            </div>
            <div className='flex flex-row items-center space-x-1'>
                <label htmlFor="" className='whitespace-nowrap w-[70px] shrink-0'>
                    {t('textinput.model')}
                </label>
                <ModelList value={tempProperties.prompt.properties.model} className="h-8 w-[200px]" onChange={onModelChange} />
            </div>
            <div className='flex flex-row items-center space-x-1 w-[275px]'>
                <label htmlFor="" className='whitespace-nowrap w-[70px] shrink-0'>
                    {t('textinput.temperature')}
                </label>
                <InputNumber min={0} max={1} step={0.1}
                    value={Number(tempProperties.prompt?.properties?.temperature)}
                    onChange={onTemperatureChange} className="w-full"
                ></InputNumber>
            </div>
            <div className='flex flex-row items-center'>
                <span className='flex flex-row items-center whitespace-nowrap w-[70px] shrink-0'>
                </span>
                <Button
                    className='h-8 w-20'
                    onClick={handleConfirm}
                >
                    {t('textinput.complete')}
                </Button>
            </div>
        </div>
    )
},TextInputPropsEqual)
