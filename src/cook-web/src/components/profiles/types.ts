type ProfileType = 'text';
type ProfileScope = 'system' | 'user';

interface Profile {
  profile_id?: string;
  parent_id?: string;
  profile_key: string;
  profile_type: ProfileType;
  profile_remark?: string;

  profile_scope?: ProfileScope;
  scope?: string;
  defaultValue?: string;
}

export type { ProfileType, Profile };
