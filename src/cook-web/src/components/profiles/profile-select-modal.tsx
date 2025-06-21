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
import { Plus } from 'lucide-react'
import ProfileSelect from './profile-select'
import type { Profile } from '@/components/profiles/type'

interface ProfileSelectModalProps {
  isDialogOpen: boolean
  setIsDialogOpen: React.Dispatch<React.SetStateAction<boolean>>
  onAddProfile: (profile: Profile) => void
  // onCancel?: () => void
}

export default function ProfileSelectModal ({
  isDialogOpen,
  setIsDialogOpen,
  onAddProfile
}: // onCancel
ProfileSelectModalProps) {
  // const [selectedProfile, setSelectedProfile] = useState<Profile | null>(null)
  const handleProfileSelect = (profile: Profile) => {
    // setSelectedProfile(profile)
    onAddProfile(profile)
  }

  // const handleCancel = () =s> {
  //   setSelectedProfile(null)
  //   setIsDialogOpen(false)
  //   // onCancel?.()
  // }

  return (
    <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
      <DialogTrigger asChild>
        <Button variant={'outline'} size='sm' className='h-8'>
          <Plus className='h-4 w-4 mr-1' />
          添加
        </Button>
      </DialogTrigger>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>添加变量</DialogTitle>
        </DialogHeader>
        <div className='space-y-4 pt-4'>
          <ProfileSelect onSelect={handleProfileSelect} />
          {/* <div className='flex justify-end space-x-2'>
            <Button variant='outline' onClick={handleCancel}>
              取消
            </Button>
            <Button
              onClick={() => {
                selectedProfile && onAddProfile(selectedProfile)
              }}
              disabled={!selectedProfile}
            >
              添加
            </Button>
          </div> */}
        </div>
      </DialogContent>
    </Dialog>
  )
}
