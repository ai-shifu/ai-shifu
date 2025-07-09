'use client'
// import { useShifu } from '@/store'
import AI from './ai'
import SolidContent from './solid-content'
import { useState, memo } from 'react'
import { useTranslation } from 'react-i18next'
import _ from 'lodash'
import { ContentDTO, UIBlockDTO } from '@/types/shifu'


const RenderBlockContentPropsEqual = (prevProps: UIBlockDTO, nextProps: UIBlockDTO) => {
  const isSame = _.isEqual(prevProps.data.bid, nextProps.data.bid) && prevProps.data.type === nextProps.data.type
  if (!isSame) {
    return false
  }

  const prevKeys = Object.keys(prevProps.data.properties || {})
  const nextKeys = Object.keys(nextProps.data.properties || {})
  if (prevKeys.length !== nextKeys.length) {
    return false
  }
  if (!_.isEqual(prevProps.data.properties, nextProps.data.properties)) {
    return false
  }
  return true
}

export const RenderBlockContent = memo(function RenderBlockContent(props: UIBlockDTO) {
  const { data } = props
  const properties = data.properties as ContentDTO

  const [error] = useState('')

  const onPropertiesChange = async properties => {
    props.onPropertiesChange(properties)
  }


  const isEdit = true
  const Ele = properties.llm_enabled ? AI : SolidContent

  return (
    <div className='bg-[#F5F5F4]'>
      <div>
        <Ele
          {...props}
          isEdit={isEdit}
          onPropertiesChange={onPropertiesChange}
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
      type: 'content',
      name: t('render-ui.content'),
      properties: {
        content: '',
        llm_enabled: true,
        llm: '',
        llm_temperature: '0.40',

      }
    },
    {
      type: 'button',
      name: t('render-ui.button'),
      properties: {
        label: {
          lang: {
            'zh-CN': '继续',
            'en-US': 'Continue'
          }
        }
      }
    },
    {
      type: 'login',
      name: t('render-ui.login'),
      properties: {
        label: {
          lang: {
            'zh-CN': '登录',
            'en-US': 'Login'
          }
        }
      }
    },
    {
      type: 'payment',
      name: t('render-ui.payment'),
      properties: {
        label: {
          lang: {
            'zh-CN': '支付',
            'en-US': 'Payment'
          }
        }
      }
    },
    {
      type: 'options',
      name: t('render-ui.option'),
      properties: {
        result_variable_bid: '',
        "options": [
          {
            "label": {
              "lang": {
                "zh-CN": "",
                "en-US": ""
              }
            },
            "value": ""
          }
        ]
      }
    },
    {
      type: 'goto',
      name: t('render-ui.goto'),
      properties: {
        conditions: [
          {
            "value": "",
            "destination_type": "",
            "destination_bid": ""
          }
        ]
      }
    },
    {
      type: 'input',
      name: t('render-ui.textinput'),
      properties: {
        placeholder: {
          lang: {
            'zh-CN': '请输入',
            'en-US': 'Please enter'
          }
        },
        prompt: '',
        result_variable_bids: [],
        llm: '',
        llm_temperature: '0.40'
      }
    }
  ]
}
