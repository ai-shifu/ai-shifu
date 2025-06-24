// TODO: remove this file when the issue is resolved

'use client'

import React from 'react'
import Image from 'next/image'

export default function TestImagesPage() {
  const testImageUrl = 'https://resource.ai-shifu.cn/ec2da124-c927-45c3-87cb-0a2ba9df66c3.jpg'

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">External Image Test</h1>
      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Test Image from resource.ai-shifu.cn:</h2>
          <div className="relative w-64 h-64 border border-gray-300">
            <Image
              src={testImageUrl}
              alt="Test external image"
              fill
              className="object-cover"
              onError={(e) => console.error('Image failed to load:', e)}
              onLoad={() => console.log('Image loaded successfully')}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
