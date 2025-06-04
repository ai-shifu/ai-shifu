/** inject image to mc-editor */
import React, { useState } from 'react'
import { ImageUploader } from '@/components/file-uploader'
import { Button } from '@/components/ui/button'
import { useTranslation } from 'react-i18next'
type ImageResource = {
  resourceUrl?: string
  resourceTitle?: string
  resourceScale?: number
}
type ImageInjectProps = {
  value: ImageResource
  onSelect: (resource: ImageResource) => void
}

const ImageInject: React.FC<ImageInjectProps> = ({ value, onSelect }) => {
  const [resource, setResource] = useState<ImageResource>({
    resourceUrl: value?.resourceUrl || '',
    resourceTitle: value?.resourceTitle || '',
    resourceScale: value?.resourceScale || 100
  })
  const { t } = useTranslation()
  const handleSelect = () => {
    onSelect({
      ...resource,
      resourceTitle: resource.resourceTitle || t('common.image-name')
    })
  }
  const handleImageChange = (resource: ImageResource) => {
    setResource(resource)
  }
  return (
    <div>
      <ImageUploader value={resource} onChange={handleImageChange} />
      <div className='flex py-4 justify-end'>
        <Button className='h-8' onClick={handleSelect} disabled={!resource?.resourceUrl}>
          {t('common.use-image')}
        </Button>
      </div>
    </div>
  )
}

export default ImageInject
