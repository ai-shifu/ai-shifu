import React, { useState } from 'react'
import { Input } from '../ui/input'
import { TextareaAutosize } from '@/components/ui/textarea-autosize'
import InputNumber from '@/components/input-number'
import ModelList from '@/components/model-list'
import { Button, ButtonProps } from '../ui/button'
import { useTranslation } from 'react-i18next';
import { memo } from 'react'
interface TextInputProps {
    properties: {
        "prompt": {
            "properties": {
                "prompt": string,
                "profiles": string[],
                "model": string,
                "temprature": string,
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
    if (prevProps.properties.input_name !== nextProps.properties.input_name
        || prevProps.properties.input_key !== nextProps.properties.input_key
        || prevProps.properties.input_placeholder !== nextProps.properties.input_placeholder
        || prevProps.properties.prompt.properties.prompt !== nextProps.properties.prompt.properties.prompt
        || prevProps.properties.prompt.properties.model !== nextProps.properties.prompt.properties.model
    ) {
        return false
    }
    if (prevProps.properties.prompt.properties.temprature !== nextProps.properties.prompt.properties.temprature) {
        return false
    }
    if (prevProps.properties.prompt.properties.profiles.length !== nextProps.properties.prompt.properties.profiles.length) {
        return false
    }
    for (let i = 0; i < prevProps.properties.prompt.properties.profiles.length; i++) {
        if (prevProps.properties.prompt.properties.profiles[i] !== nextProps.properties.prompt.properties.profiles[i]) {
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
    const onValueChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
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
                    prompt: e.target.value
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
                    temprature: value.toString()
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
            <div className='flex flex-row items-center space-x-1'>
                <label htmlFor="" className='whitespace-nowrap w-[70px] shrink-0'>
                    {t('textinput.prompt')}
                </label>
                <TextareaAutosize
                    value={tempProperties.prompt.properties.prompt}
                    onChange={onValueChange}
                    placeholder={t('textinput.prompt-placeholder')}
                    maxRows={20}

                />
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
                    value={Number(tempProperties.prompt?.properties?.temprature)}
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
