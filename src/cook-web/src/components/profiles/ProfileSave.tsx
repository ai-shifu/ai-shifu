/** inject profile to mc-editor */
'use client';
import React, { useState, useEffect } from 'react';

import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogOverlay,
} from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import type { Profile } from '@/components/profiles/types';
import api from '@/api';
import { useTranslation } from 'react-i18next';
interface ProfileSaveProps {
  parentId?: string;
  value?: Profile;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  onSaveSuccess?: (profile: Profile) => void;
}

const ProfileSave: React.FC<ProfileSaveProps> = ({
  parentId,
  value,
  open,
  onOpenChange,
  onSaveSuccess = () => {},
}) => {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(!!value?.profile_id);
  const [editingId, setEditingId] = useState<string>();
  const [profile, setProfile] = useState<Profile>({
    profile_key: '',
    profile_type: 'text',
  });

  const resetForm = () => {
    setProfile({
      profile_key: '',
      profile_type: 'text',
    });
    setIsEditing(false);
    setEditingId(undefined);
  };

  const handleSaveProfile = async () => {
    const trimmedKey = profile.profile_key.trim();
    if (!trimmedKey) {
      return;
    }

    const profileToSave: Profile = {
      ...profile,
      profile_key: trimmedKey,
      profile_type: 'text',
      profile_id: editingId,
      parent_id: parentId,
      profile_remark: '',
    };
    const res = await api.saveProfile(profileToSave).catch(error => {
      console.error('Failed to save profile:', error);
      return null;
    });
    if (res) {
      onSaveSuccess?.(profileToSave);
      resetForm();
      onOpenChange?.(false);
    }
  };

  const handleCancelSaveProfile = async () => {
    resetForm();
    onOpenChange?.(false);
  };

  useEffect(() => {
    if (value) {
      setEditingId(value.profile_id);
      setIsEditing(!!value.profile_id);
      setProfile({
        profile_key: value.profile_key,
        profile_type: 'text',
      });
      return;
    }

    setProfile({
      profile_key: '',
      profile_type: 'text',
    });
    setIsEditing(false);
    setEditingId(undefined);
  }, [value]);

  return (
    <Dialog
      open={open}
      onOpenChange={isOpen => {
        if (!isOpen) {
          resetForm();
        }
        onOpenChange?.(isOpen);
      }}
    >
      <DialogOverlay
        className='fixed inset-0 bg-black/50 z-[100]'
        onClick={e => {
          e.preventDefault();
          e.stopPropagation();
        }}
      />
      <DialogContent className='z-[101] sm:max-w-[500px]'>
        <DialogHeader>
          <DialogTitle>
            {isEditing
              ? t('module.profiles.editVariable')
              : t('module.profiles.addNewVariable')}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? t('module.profiles.modifyExistingVariable')
              : t('module.profiles.createNewCustomVariable')}
          </DialogDescription>
        </DialogHeader>
        <div className='grid gap-4 py-4'>
          <div className='grid grid-cols-4 items-center gap-4'>
            <Label
              htmlFor='profile_key'
              className='text-right'
            >
              {t('module.profiles.variableName')}
            </Label>
            <Input
              id='profile_key'
              value={profile.profile_key}
              onChange={e =>
                setProfile({ ...profile, profile_key: e.target.value })
              }
              className='col-span-3'
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            className='h-8'
            variant='outline'
            onClick={handleCancelSaveProfile}
          >
            {t('module.profiles.cancel')}
          </Button>
          <Button
            className='h-8'
            onClick={handleSaveProfile}
            disabled={!profile.profile_key.trim()}
          >
            {isEditing ? t('module.profiles.save') : t('module.profiles.add')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
export default ProfileSave;
