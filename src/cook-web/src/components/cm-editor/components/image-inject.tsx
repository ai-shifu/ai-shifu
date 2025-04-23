/** inject image to mc-editor */
import Button from '@/components/button'
import React from 'react'

type ImageInjectProps = {
  onSelect: (url: string) => void
}

const ImageInject: React.FC<ImageInjectProps> = ({ onSelect }) => {
  const handleClick  = () => {
    // TODO：test code
    const imageUrl = 'https://github.com/shadcn.png'
    onSelect(imageUrl)
  }
  return (
    <div>
      <div>图片上传的组件接入到这个组件</div>
      <Button onClick={handleClick}>插入测试图片</Button>
    </div>
  )
}

export default ImageInject
