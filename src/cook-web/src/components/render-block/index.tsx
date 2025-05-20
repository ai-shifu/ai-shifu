'use client'
import { useShifu } from '@/store'
import AI from './ai'
import SolidContent from './solid-content'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

const BlockMap = {
  ai: AI,
  solidcontent: SolidContent
}

interface IRenderBlockContentProps {
  id: string
  type: any
  properties: any
}

export const RenderBlockContent = ({
  id,
  type,
  properties
}: IRenderBlockContentProps) => {
  const { t } = useTranslation()
  const {
    actions,
    blocks,
    blockContentTypes,
    currentNode,
    blockUITypes,
    blockContentProperties,
    blockUIProperties,
    currentShifu
  } = useShifu()
  const [error, setError] = useState('')
  // const ContentTypes = useContentTypes()

  const onPropertiesChange = async properties => {
    await actions.setBlockContentPropertiesById(id, properties)
    const p = {
      ...blockContentProperties,
      [id]: {
        ...blockContentProperties[id],
        ...properties
      }
    }
    setError('')
    if (type == 'ai' && properties.prompt == '') {
      setError(t('render-block.ai-content-empty'))
      return
    } else if (type == 'solidcontent' && properties.content == '') {
      setError(t('render-block.solid-content-empty'))
      return
    }
    if (currentNode) {
      actions.autoSaveBlocks(
        currentNode.id,
        blocks,
        blockContentTypes,
        p,
        blockUITypes,
        blockUIProperties,
        currentShifu?.shifu_id || ''
      )
    }
  }

  // const onContentTypeChange = (id: string, type: string) => {
  //   const opt = ContentTypes.find(p => p.type === type)
  //   actions.setBlockContentTypesById(id, type)
  //   actions.setBlockContentPropertiesById(
  //     id,
  //     opt?.properties || ({} as any),
  //     true
  //   )
  // }

  const onSave = async () => {
    setError('')
    const block = blocks.find(item => item.properties.block_id == id)
    if (type == 'ai' && block && properties.prompt == '') {
      setError(t('render-block.ai-content-empty'))
      return
    } else if (type == 'solidcontent' && block && properties.content == '') {
      setError(t('render-block.solid-content-empty'))
      return
    }
    await actions.saveBlocks(currentShifu?.shifu_id || '')
  }

  const isEdit = true
  const Ele = BlockMap[type]
  return (
    <div className='bg-[#F5F5F4]'>
      {/* {
                isEdit && (
                    <div className='rounded-t-md p-2 flex flex-row items-center py-1 justify-between'>
                        <Select
                            value={blockContentTypes[id]}
                            onValueChange={onContentTypeChange.bind(null, id)}
                        >
                            <SelectTrigger className="h-8 w-[120px]">
                                <SelectValue placeholder={t('render-block.select-content-type')} />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectGroup>
                                    {
                                        ContentTypes.map((item) => {
                                            return (
                                                <SelectItem key={item.type} value={item.type}>{item.name}</SelectItem>
                                            )
                                        })
                                    }
                                </SelectGroup>
                            </SelectContent>
                        </Select>
                        <div className='flex flex-row items-center'>
                            <div className='flex flex-row items-center px-2' onClick={onRemove}>
                                <Trash2 className='h-5 w-5 cursor-pointer' />
                            </div>
                            <div className='h-4 border-r border-[#D8D8D8] mx-1'></div>
                        </div>
                    </div>
                )
            } */}

      <div>
        <Ele
          isEdit={isEdit}
          properties={properties}
          onChange={onPropertiesChange}
          onBlur={onSave}
        />
      </div>
      {error && <div className='text-red-500 text-sm px-2 pb-2'>{error}</div>}
    </div>
  )
}

export default RenderBlockContent

export const useContentTypes = () => {
  const { t } = useTranslation()
  return [
    {
      type: 'ai',
      name: t('render-block.ai-content'),
      properties: {
        prompt: '',
        profiles: [],
        model: '',
        temprature: '0.40',
        other_conf: ''
      }
    },
    {
      type: 'solidcontent',
      name: t('render-block.solid-content'),
      properties: {
        content: '',
        profiles: []
      }
    }
  ]
}
