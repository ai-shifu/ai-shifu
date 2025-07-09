import React, { useState } from 'react'
import { Input } from '../ui/input'
import { Editor } from '@/components/cm-editor'
import InputNumber from '@/components/input-number'
import ModelList from '@/components/model-list'
import { Button } from '../ui/button'
import { useTranslation } from 'react-i18next'
import { memo } from 'react'
import _ from 'lodash'
import { ProfileFormItem } from '@/components/profiles'
import { InputDTO, UIBlockDTO } from '@/types/shifu'
import i18n from '@/i18n'

const TextInputPropsEqual = (
  prevProps: UIBlockDTO,
  nextProps: UIBlockDTO
) => {
  const prevInputSettings = prevProps.data.properties as InputDTO
  const nextInputSettings = nextProps.data.properties as InputDTO
  if (!_.isEqual(prevProps.data, nextProps.data)) {
    return false
  }
  if (!_.isEqual(prevInputSettings.prompt, nextInputSettings.prompt)) {
    return false
  }
  if (!_.isEqual(prevInputSettings.placeholder, nextInputSettings.placeholder)) {
    return false
  }
  return true
}

function TextInput(props: UIBlockDTO) {
  const { data, onChanged } = props
  const [tempProperties, setTempProperties] = useState(data.properties as InputDTO)
  const [changed, setChanged] = useState(false)
  const { t } = useTranslation()
  const onValueChange = (value: string) => {
    if (!changed) {
      setChanged(true)
      onChanged?.(true)
    }
    setTempProperties({
      ...tempProperties,
      prompt: value
    })
  }

  const onModelChange = (value: string) => {
    setTempProperties({
      ...tempProperties,
      llm: value
    })
  }

  const onTemperatureChange = (value: number) => {
    setTempProperties({
      ...tempProperties,
      llm_temperature: value
    })
  }

  const handleProfileChange = (value: string[]) => {
    console.log('handleProfileChange', value)
    // Ensure that both `profiles` (nested) and `profile_ids` (top-level) are updated in sync
    setTempProperties({
      ...tempProperties,
      result_variable_bids: value
    })
  }

  const onInputPlaceholderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTempProperties({
      ...tempProperties,
      placeholder: {
        ...tempProperties.placeholder,
        lang: {
          'zh-CN': e.target.value,
          'en-US': e.target.value
        }
      }
    })
  }

  const handleConfirm = () => {
    props.onPropertiesChange({
      ...data,
      properties: tempProperties,
      variable_bids: tempProperties.result_variable_bids
    })
  }

  return (
    <div className='flex flex-col space-y-2 w-full'>
      <div className='flex flex-row items-center space-x-1'>
        <label htmlFor='' className='whitespace-nowrap w-[70px] shrink-0'>
          {t('textinput.input-placeholder')}
        </label>
        <Input
          value={tempProperties.placeholder.lang[i18n.language]}
          onChange={onInputPlaceholderChange}
          className='w-full'
        ></Input>
      </div>
      <div className='flex flex-row items-center space-x-1'>
        <label htmlFor='' className='whitespace-nowrap w-[70px] shrink-0'>
          {t('textinput.input-name')}
        </label>
        <ProfileFormItem
          value={tempProperties?.result_variable_bids}
          onChange={handleProfileChange}
        />
      </div>
      <div className='flex flex-row items-center space-x-1'>
        <label htmlFor='' className='whitespace-nowrap w-[70px] shrink-0'>
          {t('textinput.prompt')}
        </label>
        <div className='w-full rounded-md border bg-background px-1 py-1'>
          <div
            style={{ minHeight: '72px', maxHeight: '480px', overflowY: 'auto' }}
          >
            <Editor
              content={tempProperties.prompt}
              onChange={onValueChange}
              isEdit={true}
            />
          </div>
        </div>
      </div>
      <div className='flex flex-row items-center space-x-1'>
        <label htmlFor='' className='whitespace-nowrap w-[70px] shrink-0'>
          {t('textinput.model')}
        </label>
        <ModelList
          value={tempProperties.llm}
          className='h-8 w-[200px]'
          onChange={onModelChange}
        />
      </div>
      <div className='flex flex-row items-center space-x-1 w-[275px]'>
        <label htmlFor='' className='whitespace-nowrap w-[70px] shrink-0'>
          {t('textinput.temperature')}
        </label>
        <InputNumber
          min={0}
          max={1}
          step={0.1}
          value={Number(tempProperties.llm_temperature)}
          onChange={onTemperatureChange}
          className='w-full'
        ></InputNumber>
      </div>
      <div className='flex flex-row items-center'>
        <span className='flex flex-row items-center whitespace-nowrap w-[70px] shrink-0'></span>
        <Button className='h-8 w-20' onClick={handleConfirm}>
          {t('textinput.complete')}
        </Button>
      </div>
    </div>
  )
}

export default memo(TextInput, TextInputPropsEqual)
