'use client'
import { useShifu } from '@/store'
import AI from './ai'
import SolidContent from './solid-content'
import { useState ,memo} from 'react'
import { useTranslation } from 'react-i18next'
import _ from 'lodash'

const BlockMap = {
  ai: AI,
  solidcontent: SolidContent
}

interface IRenderBlockContentProps {
  id: string
  type: any
  properties: any
}


const RenderBlockContentPropsEqual = (prevProps: IRenderBlockContentProps, nextProps: IRenderBlockContentProps) => {
  const isSame = _.isEqual(prevProps.id, nextProps.id) && prevProps.type === nextProps.type
  if (!isSame) {
    return false
  }

  const prevKeys = Object.keys(prevProps.properties || {})
  const nextKeys = Object.keys(nextProps.properties || {})
  if (prevKeys.length !== nextKeys.length) {
    return false
  }
  if (!_.isEqual(prevProps.properties, nextProps.properties)) {
    return false
  }
  return true
}
export const RenderBlockContent = memo(({
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
        currentNode.bid,
        blocks,
        blockContentTypes,
        p,
        blockUITypes,
        blockUIProperties,
        currentShifu?.bid || ''
      )
    }
  }

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
    await actions.saveBlocks(currentShifu?.bid || '')
  }

  const isEdit = true
  const Ele = BlockMap[type]
  return (
    <div className='bg-[#F5F5F4]'>
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
}, RenderBlockContentPropsEqual)

RenderBlockContent.displayName = 'RenderBlockContent'

export default RenderBlockContent

export const useContentTypes = () => {
  const { t } = useTranslation()
  return [
    {
      type: 'ai',
      name: t('render-block.ai-content'),
      properties: {
        prompt: '',
        variables: [],
        model: '',
        temperature: '0.40',
        other_conf: ''
      }
    },
    {
      type: 'solidcontent',
      name: t('render-block.solid-content'),
      properties: {
        prompt: '',
        variables: []
      }
    }
  ]
}
