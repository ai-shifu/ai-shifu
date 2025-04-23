import { useState, useEffect } from 'react'
import type { Profile } from './type'
import api from '@/api'

type useProfileParams = {
  parentId?: string
  searchTerm: string
  refreshFlag?: number
}
const useProfiles = ({
  parentId,
  searchTerm,
  refreshFlag
}: useProfileParams) => {
  const [profiles, setProfiles] = useState<Profile[]>()
  const fetchList = async () => {
    const list = await api.getProfileList({
        parent_id: parentId
      })
    setProfiles(list as unknown as Profile[])
  }

  const getProfilesByType = (profiles: Profile[] | undefined) => {
    const filteredProfiles = profiles?.filter(
      profile =>
        profile.profile_key.toLowerCase().includes(searchTerm.toLowerCase()) ||
        profile.profile_key.toLowerCase().includes(searchTerm.toLowerCase())
    )
    const systemProfiles = filteredProfiles?.filter(v => v.profile_scope === 'system')
    const customProfiles = filteredProfiles?.filter(v => v.profile_scope === 'user')
    return [systemProfiles, customProfiles]
  }

  useEffect(() => {
    fetchList()
  }, [parentId, refreshFlag])

  return getProfilesByType(profiles)
}

export default useProfiles
