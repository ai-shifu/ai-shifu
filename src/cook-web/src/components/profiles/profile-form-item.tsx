'use client'

import type React from 'react'
import { useState, useEffect } from 'react'
import { Badge } from '@/components/ui/badge'
import { X } from 'lucide-react'
import ProfileSelectModal from './profile-select-modal'
import useProfiles from './useProfiles'
import type { Profile } from '@/components/profiles/type'

interface ProfileFormItemProps {
  value: string[]
  onChange?: (value: string[]) => void
}

export default function ProfileFormItem ({
  value,
  onChange
}: ProfileFormItemProps) {
  const [selectedProfiles, setSelectedProfiles] = useState<Profile[] | []>([])
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [systemProfiles, customProfiles] = useProfiles()

  const handleAddProfile = (profile: Profile) => {
    setIsDialogOpen(false)
    if (
      profile.profile_id &&
      !selectedProfiles.find(item => item.profile_id === profile.profile_id)
    ) {
      const currentProfiles = [...selectedProfiles, profile]
      setSelectedProfiles(currentProfiles)
      onChange?.(currentProfiles.map(profile => profile.profile_id || ''))
    }
  }

  const handleRemoveProfileKey = (index: number) => {
    const currentProfiles = [...selectedProfiles]
    currentProfiles.splice(index, 1)
    setSelectedProfiles(currentProfiles)
    onChange?.(currentProfiles.map(profile => profile.profile_id || ''))
  }

  useEffect(() => {
    const profiles = [...(systemProfiles || []), ...(customProfiles || [])]
    const selectedProfiles = profiles.filter(
      profile => profile?.profile_id && value?.includes(profile.profile_id)
    )
    setSelectedProfiles(selectedProfiles)
  }, [JSON.stringify(systemProfiles), JSON.stringify(customProfiles)])

  return (
    <div className='py-2 flex items-center justify-between gap-6'>
      {!!selectedProfiles?.length && (
        <div className='flex flex-wrap gap-2'>
          {selectedProfiles?.map((profile: Profile, index: number) => (
            <Badge
              key={index}
              variant='outline'
              className='flex items-center gap-1'
            >
              {profile.profile_key}
              <button
                onClick={() => handleRemoveProfileKey(index)}
                className='ml-1 hover:bg-destructive/20 rounded-full p-0.5'
              >
                <X className='h-3 w-3' />
              </button>
            </Badge>
          ))}
        </div>
      )}
      {selectedProfiles?.length < 1 && (
        <ProfileSelectModal
          isDialogOpen={isDialogOpen}
          setIsDialogOpen={setIsDialogOpen}
          onAddProfile={handleAddProfile}
        />
      )}
    </div>
  )
}
