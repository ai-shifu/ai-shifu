type ProfileType = 'text' | 'option';
type ProfileScope = 'system' | 'user';

interface EnumItem {
  value: string;
  name: string;
}

interface Profile {
  profile_id?: string;
  parent_id?: string;
  profile_key: string;
  profile_type: ProfileType;
  profile_remark: string;
  profile_items?: EnumItem[];

  profile_scope?: ProfileScope;
  scope?: string;
  defaultValue?: string;
}

export type { ProfileType, EnumItem, Profile };
