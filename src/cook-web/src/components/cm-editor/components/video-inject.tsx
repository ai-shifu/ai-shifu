/** inject Video to mc-editor */
import Button from '@/components/button'
import React from 'react'

type VideoInjectProps = {
  onSelect: (resourceUrl: string) => void
}

const VideoInject: React.FC<VideoInjectProps> = ({ onSelect }) => {
  const handleClick  = () => {
    // TODO：test code
    const videoUrl = 'https://github.com/shadcn.mp4'
    onSelect(videoUrl)
  }
  return (
    <div>
      <div>视频上传的组件接入到这个组件</div>
      <Button onClick={handleClick}>插入测试视频</Button>
    </div>
  )
}

export default VideoInject
