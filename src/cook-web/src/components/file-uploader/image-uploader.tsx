'use client'

import type React from 'react'

import { useState, useRef, useEffect } from 'react'
import { Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { uploadFile } from '@/lib/file'
import { getSiteHost } from "@/config/runtime-config";

type ImageUploaderProps = {
  value?: string
  onChange?: (value: string) => void
}

const ImageUploader:React.FC<ImageUploaderProps> = ({
  value,
  onChange,
}) => {
  const [imageUrl, setImageUrl] = useState<string>(value ||'')
  const [inputUrl, setInputUrl] = useState<string>('')
  const [isUploading, setIsUploading] = useState<boolean>(false)
  const [fileName, setFileName] = useState<string>('')
  const [uploadProgress, setUploadProgress] = useState(0)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const siteHost = getSiteHost()

  const resetState = () => {
    setImageUrl('')
    setInputUrl('')
    setFileName('')
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const uploadImage = async (file: File) => {
    setIsUploading(true)
    try {
      const response = await uploadFile(
        file,
        `${siteHost}/api/scenario/upfile`,
        undefined,
        undefined,
        progress => {
          setUploadProgress(progress)
        }
      )

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`)
      }

      const res = await response.json()
      if (res.code !== 0) {
        throw new Error(res.message)
      }

      if (!response.ok) {
        throw new Error('Upload failed')
      }

      setImageUrl(res.data)
      setFileName(file.name)
      const img = new Image()
      img.src = res.data
    } catch (error) {
      console.error('Error uploading image:', error)
      alert('Failed to upload image')
    } finally {
      setIsUploading(false)
    }
  }

  const handleUrlUpload = async () => {
    if (!inputUrl) return
    const urlParts = inputUrl.split('/')
    setFileName(urlParts[urlParts.length - 1])
    setImageUrl(inputUrl)
    setIsUploading(false)
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      uploadImage(file)
    }
  }

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const file = e.dataTransfer.files?.[0]
    if (file) {
      uploadImage(file)
    }
  }

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
  }

  useEffect(() => {
    onChange?.(imageUrl)
  },[imageUrl])

  return (
    <div className='space-y-6'>
      {!imageUrl ? (
        <>
          <div className='text-xs'>
            <h2 className='font-bold mb-4'>URL</h2>
            <div className='flex gap-2'>
              <Input
                placeholder='粘贴或输入图片 URL'
                value={inputUrl}
                onChange={e => setInputUrl(e.target.value)}
                className='flex-1'
              />
              <Button
                onClick={handleUrlUpload}
                disabled={isUploading || !inputUrl}
                className='w-24 h-8'
              >
                运行
              </Button>
            </div>
          </div>

          <div>
            <h2 className='font-bold mb-4'>上传</h2>
            <Card
              className='border-dashed border-2 text-center flex flex-col items-center justify-center min-h-[200px] p-2'
              onDrop={handleDrop}
              onDragOver={handleDragOver}
            >
              {isUploading ? (
                <div className='mt-2'>
                  <div className='w-full bg-gray-200 rounded-full h-2.5'>
                    <div
                      className='bg-primary h-2.5 rounded-full'
                      style={{ width: `${uploadProgress}%` }}
                    ></div>
                  </div>
                  <p className='text-xs text-gray-500 mt-1 text-center'>
                    上传中 {uploadProgress}%
                  </p>
                </div>
              ) : (
                <>
                  <input
                    type='file'
                    ref={fileInputRef}
                    onChange={handleFileChange}
                    className='hidden'
                    accept='image/*'
                  />
                  <Upload className='h-10 w-10 text-gray-400 mb-4' />
                  <div className='mb-2'>
                    拖动文件或者
                    <button
                      className='text-blue-600 hover:underline'
                      onClick={() => fileInputRef.current?.click()}
                    >
                      点击上传
                    </button>
                  </div>
                  <p className='text-gray-500'>
                    提示：您还可以将图片拖动或粘贴到卡片中的任意位置
                  </p>
                </>
              )}
            </Card>
          </div>
        </>
      ) : (
        <div className='flex flex-col items-center'>
          <img
            src={imageUrl || '/placeholder.svg'}
            alt='Uploaded image'
            className='max-w-full max-h-[400px] object-contain mb-4'
          />
          <div className=' mb-6'>{fileName}</div>
          <Button
              variant='outline'
              className='w-full py-6 text-lg'
              onClick={resetState}
            >
              替换图片
            </Button>
        </div>
      )}
    </div>
  )
}

export default ImageUploader
