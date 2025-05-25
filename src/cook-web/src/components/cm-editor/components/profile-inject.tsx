/** inject variable to mc-editor */
'use client'
import React, { useCallback } from 'react'
import ProfileSelect from '@/components/profiles/profile-select'
import type { Profile } from '@/components/profiles/type'
import { useShifu } from '@/store'

type ProfileInjectProps = {
  value?: string
  onSelect: (profile: Profile) => void
}
const ProfileInject: React.FC<ProfileInjectProps> = ({
  value,
  onSelect = () => {}
}) => {
  const { currentShifu } = useShifu()
  const handleSelect = useCallback((profile: Profile) => {
    onSelect?.(profile)
  }, [])

  return <ProfileSelect value={value} parentId={currentShifu?.shifu_id as unknown as string} onSelect={handleSelect} />
}
export default ProfileInject
