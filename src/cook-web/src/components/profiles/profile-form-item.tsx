'use client'

import type React from 'react'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Plus, X } from 'lucide-react'
import ProfileSelect from './profile-select'

interface ProfileKeyManagerProps {
  value: string[]
  onChange: (value: string[]) => void
}

export default function ProfileKeyManager ({
  value,
  onChange
}: ProfileKeyManagerProps) {
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [newProfileKey, setNewProfileKey] = useState('')

  const handleAddProfileKey = () => {
    if (newProfileKey.trim() && !value.includes(newProfileKey.trim())) {
      onChange([...value, newProfileKey.trim()])
      setNewProfileKey('')
      setIsDialogOpen(false)
    }
  }

  const handleRemoveProfileKey = (keyToRemove: string) => {
    onChange(value.filter(key => key !== keyToRemove))
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleAddProfileKey()
    }
  }

  return (
    <div className='space-y-4'>
      <div className='flex items-center justify-between'>
        <Label className='text-sm font-medium'>Profile Keys</Label>
        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogTrigger asChild>
            <Button size='sm' className='h-8'>
              <Plus className='h-4 w-4 mr-1' />
              添加
            </Button>
          </DialogTrigger>
          <DialogContent className='sm:max-w-md'>
            <DialogHeader>
              <DialogTitle>添加变量</DialogTitle>
            </DialogHeader>
            <div className='space-y-4 pt-4'>
              <ProfileSelect value={newProfileKey} onSelect={() => {}} />
              <div className='flex justify-end space-x-2'>
                <Button
                  variant='outline'
                  onClick={() => {
                    setIsDialogOpen(false)
                    setNewProfileKey('')
                  }}
                >
                  取消
                </Button>
                <Button
                  onClick={handleAddProfileKey}
                  disabled={
                    !newProfileKey.trim() ||
                    value.includes(newProfileKey.trim())
                  }
                >
                  添加
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <div className='min-h-[60px] p-3 border rounded-md bg-muted/30'>
        {value.length === 0 ? (
          <p className='text-sm text-muted-foreground'>暂无 Profile Key</p>
        ) : (
          <div className='flex flex-wrap gap-2'>
            {value.map((profileKey, index) => (
              <Badge
                key={index}
                variant='secondary'
                className='flex items-center gap-1'
              >
                {profileKey}
                <button
                  onClick={() => handleRemoveProfileKey(profileKey)}
                  className='ml-1 hover:bg-destructive/20 rounded-full p-0.5'
                >
                  <X className='h-3 w-3' />
                </button>
              </Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
