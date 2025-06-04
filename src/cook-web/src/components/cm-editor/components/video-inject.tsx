/** inject Video to mc-editor */
import Button from '@/components/button'
import { Input } from '@/components/ui/input'
import React, { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import api from '@/api'

type VideoInjectProps = {
  value?: {
    resourceTitle?: string
    resourceUrl?: string
  }
  onSelect: ({
    resourceUrl,
    resourceTitle
  }: {
    resourceUrl: string
    resourceTitle: string
  }) => void
}

const biliVideoUrlRegexp =
  /(https?:\/\/(?:www\.|m\.)?bilibili\.com\/video\/\S+\/?)/i

const VideoInject: React.FC<VideoInjectProps> = ({ value, onSelect }) => {
  const { t } = useTranslation()
  const [title, setTitle] = useState(value?.resourceTitle || t('common.video-title'))
  const [inputUrl, setInputUrl] = useState<string>(value?.resourceUrl || '')
  const [embedUrl, setEmbedUrl] = useState('')
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const lastUrlRef = useRef('')
  const [errorTips, setErrorTips] = useState('')

  const isValidBilibiliUrl = (url: string) => {
    return biliVideoUrlRegexp.test(url)
  }

  const generateEmbedUrl = (url: string) => {
    const encoded = encodeURIComponent(url)
    return `https://if-cdn.com/api/iframe?url=${encoded}&key=a68bac8b6624d46b6d0ba46e5b3f8971`
  }

  const handleRun = () => {
    setErrorTips('')
    if (!isValidBilibiliUrl(inputUrl)) {
      setErrorTips(t('common.please-input-valid-bilibili-url'))
      return
    }

    const newEmbedUrl = generateEmbedUrl(inputUrl)

    if (lastUrlRef.current === newEmbedUrl) {
      checkVideoPlayback()
      return
    }

    api.getVideoInfo({ url: inputUrl }).then(res => {
      setTitle(res.title)
    }).catch(err => {
      console.log('err', err)
      setErrorTips(t('common.please-input-valid-bilibili-url'))
    })

    setEmbedUrl(newEmbedUrl)
    lastUrlRef.current = newEmbedUrl
  }

  const handleSelect = () => {
    if (inputUrl) {
      try {
        const returnUrlObj = new URL(inputUrl)
        onSelect({
          resourceUrl: returnUrlObj.origin + returnUrlObj.pathname,
          resourceTitle: title
        })
      } catch (error) {
        console.log('error', error)
        onSelect({ resourceUrl: inputUrl, resourceTitle: title })
      }
    }
  }

  const checkVideoPlayback = () => {
    if (!iframeRef.current) return
  }

  useEffect(() => {
    if (embedUrl) {
      setTimeout(checkVideoPlayback, 2000)
    }
  }, [embedUrl])

  return (
    <div>
      <div className='flex items-center space-x-2'>
        <Input
          type='text'
          value={inputUrl}
          onChange={e => setInputUrl(e.target.value?.trim())}
          placeholder={t('common.please-input-bilibili-url')}
          autoComplete='off'
        />
        <Button className='h-8' onClick={handleRun}>
          {t('common.run')}
        </Button>
        {embedUrl && (
          <Button className='h-8' onClick={handleSelect}>
            {t('common.use-resource')}
          </Button>
        )}
      </div>
      {!!errorTips && <div>{errorTips}</div>}

      {embedUrl && (
        <div className='space-y-4'>
          <Input
            value={title}
            aria-placeholder={t('common.video-title-placeholder')}
            onChange={e => setTitle(e.target.value.slice(0, 100))}
            placeholder={t('common.video-title')}
            className='mt-4'
            maxLength={100}
          />
          <div
            style={{
              position: 'relative',
              paddingTop: '56.25%',
              marginTop: 16
            }}
          >
            <iframe
              ref={iframeRef}
              src={embedUrl}
              style={{
                top: 0,
                left: 0,
                width: '100%',
                height: '100%',
                position: 'absolute',
                border: 0
              }}
              allowFullScreen
              allow='autoplay; encrypted-media'
              title='bilibili-video'
            />
          </div>
        </div>
      )}
    </div>
  )
}
export { biliVideoUrlRegexp }
export default VideoInject
