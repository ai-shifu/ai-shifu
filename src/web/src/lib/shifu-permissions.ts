import { Shifu } from '@/types/shifu';

export const canManageArchive = (
  shifu: Shifu | null | undefined,
  currentUserId: string,
): boolean => {
  if (!shifu?.bid) {
    return false;
  }
  if (typeof shifu.can_manage_archive === 'boolean') {
    return shifu.can_manage_archive;
  }
  if (shifu.created_user_bid) {
    return shifu.created_user_bid === currentUserId;
  }
  return !shifu.readonly;
};

export const canManageOwnerCourseAction = (
  shifu: Shifu | null | undefined,
  currentUserId: string,
): boolean => {
  if (!shifu?.bid || !currentUserId) {
    return false;
  }
  return (
    Boolean(shifu.created_user_bid) && shifu.created_user_bid === currentUserId
  );
};
