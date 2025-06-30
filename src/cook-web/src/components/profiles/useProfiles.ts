import { useState, useEffect } from 'react'
import type { Profile } from './type'
import { useShifu } from '@/store'
import api from '@/api'

type useProfileParams = {
  searchTerm?: string
  refreshFlag?: number
}

const useProfiles = (props?: useProfileParams) => {
  const { searchTerm, refreshFlag } = props || {}
  const { currentShifu } = useShifu()
  const [profiles, setProfiles] = useState<Profile[]>()
  const fetchList = async () => {
    const list = await api.getProfileList({
      parent_id: currentShifu?.bid
    })
    setProfiles(list as unknown as Profile[])
  }

  const getProfilesByType = (profiles: Profile[] | undefined) => {
    const filteredProfiles = profiles?.filter(profile =>
      profile.profile_key
        .toLowerCase()
        .includes(searchTerm?.toLowerCase() || '')
    )
    const systemProfiles = filteredProfiles?.filter(
      v => v.profile_scope === 'system'
    )
    const customProfiles = filteredProfiles?.filter(
      v => v.profile_scope === 'user'
    )
    return [systemProfiles, customProfiles]
  }

  useEffect(() => {
    fetchList()
  }, [refreshFlag])

  return getProfilesByType(profiles)
}

export default useProfiles
