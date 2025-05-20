/** inject Video to mc-editor */
import Button from '@/components/button'
import { Input } from '@/components/ui/input'
import React, { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
type VideoInjectProps = {
  value?: string
  onSelect: (resourceUrl: string) => void
}

const biliVideoUrlRegexp =
  /(https?:\/\/(?:www\.|m\.)?bilibili\.com\/video\/\S+)/ig

const VideoInject: React.FC<VideoInjectProps> = ({ value, onSelect }) => {
  const { t } = useTranslation();
  const [inputUrl, setInputUrl] = useState<string>(value || '')
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
    if (!isValidBilibiliUrl(inputUrl)) {
      setErrorTips(t('common.please-input-valid-bilibili-url'))
      return
    }

    const newEmbedUrl = generateEmbedUrl(inputUrl)

    if (lastUrlRef.current === newEmbedUrl) {
      checkVideoPlayback()
      return
    }

    setEmbedUrl(newEmbedUrl)
    lastUrlRef.current = newEmbedUrl
  }

  const handleSelect = () => {
    if (inputUrl) {
      try {
        const returnUrlObj = new URL(inputUrl)
        onSelect(returnUrlObj.origin + returnUrlObj.pathname)
      } catch (error) {
        console.log('error', error)
        onSelect(inputUrl)
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
        {embedUrl && <Button className='h-8' onClick={handleSelect}>{t('common.use-resource')}</Button>}
      </div>
      {!!errorTips && <div>{errorTips}</div>}

      {embedUrl && (
        <div
          style={{ position: 'relative', paddingTop: '56.25%', marginTop: 16 }}
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
      )}
    </div>
  )
}
export { biliVideoUrlRegexp }
export default VideoInject
