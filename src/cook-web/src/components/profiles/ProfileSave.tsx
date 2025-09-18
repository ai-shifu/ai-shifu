/** inject profile to mc-editor */
'use client';
import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';

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
import { RadioGroup, RadioGroupItem } from '@/components/ui/RadioGroup';
import type {
  Profile,
  EnumItem,
  ProfileType,
} from '@/components/profiles/types';
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
  const [editingId, setEditingId] = useState<number>();
  const [profile, setProfile] = useState<Profile>({
    profile_key: '',
    profile_remark: '',
    profile_type: 'text',
    profile_items: [],
  });

  const [newEnumItem, setNewEnumItem] = useState<EnumItem>({
    value: '',
    name: '',
  });

  const resetForm = () => {
    setProfile({
      profile_key: '',
      profile_remark: '',
      profile_type: 'text',
      profile_items: [],
    });
    setNewEnumItem({ value: '', name: '' });
    setIsEditing(false);
    setEditingId(undefined);
  };

  const handleSaveProfile = async () => {
    if (profile.profile_key.trim()) {
      const profileToSave: Profile = {
        ...profile,
        profile_items:
          profile.profile_type === 'option' ? profile.profile_items : undefined,
        profile_id: editingId as unknown as string,
        parent_id: parentId,
      };
      const res = await api.saveProfile(profileToSave).catch(() => {
        // Error handling - could be logged to external service in production
        return null;
      });
      if (res) {
        onSaveSuccess?.(profileToSave);
        resetForm();
        onOpenChange?.(false);
      }
    }
  };

  const handleCancelSaveProfile = async () => {
    resetForm();
    onOpenChange?.(false);
  };

  const handleAddEnumItem = () => {
    if (newEnumItem.value.trim() && newEnumItem.name.trim()) {
      setProfile({
        ...profile,
        profile_items: [...(profile.profile_items || []), { ...newEnumItem }],
      });
      setNewEnumItem({ value: '', name: '' });
    }
  };

  const handleRemoveEnumItem = (index: number) => {
    const updatedEnumItems = [...(profile.profile_items || [])];
    updatedEnumItems.splice(index, 1);
    setProfile({
      ...profile,
      profile_items: updatedEnumItems,
    });
  };

  useEffect(() => {
    const fetchProfileItemOptionList = async () => {
      if (value) {
        setEditingId(value.profile_id as unknown as number);
        setIsEditing(!!value.profile_id);
        if (value.profile_type === 'option' && value.profile_id) {
          const res = await api.getProfileItemOptionList({
            parent_id: value.profile_id,
          });
          if (res) {
            const enumItems: EnumItem[] = res.map((item: { value: string; name: string }) => ({
              value: item.value,
              name: item.name,
            }));
            setProfile({
              ...value,
              profile_items: enumItems,
            });
          } else {
            setProfile({
              ...value,
              profile_items: [],
            });
          }
        } else {
          setProfile({
            ...value,
            profile_items: [],
          });
        }
      } else {
        resetForm();
      }
    };
    fetchProfileItemOptionList();
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
              ? t('profiles.editVariable')
              : t('profiles.addNewVariable')}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? t('profiles.modifyExistingVariable')
              : t('profiles.createNewCustomVariable')}
          </DialogDescription>
        </DialogHeader>
        <div className='grid gap-4 py-4'>
          <div className='grid grid-cols-4 items-center gap-4'>
            <Label
              htmlFor='profile_key'
              className='text-right'
            >
              {t('profiles.variableName')}
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
          <div className='grid grid-cols-4 items-center gap-4'>
            <Label
              htmlFor='title'
              className='text-right'
            >
              {t('profiles.title')}
            </Label>
            <Input
              id='profile_remark'
              value={profile.profile_remark}
              onChange={e =>
                setProfile({ ...profile, profile_remark: e.target.value })
              }
              className='col-span-3'
              placeholder={t('profiles.optional')}
            />
          </div>
          <div className='grid grid-cols-4 items-center gap-4'>
            <Label className='text-right'>{t('profiles.dataType')}</Label>
            <div className='col-span-3'>
              <RadioGroup
                value={profile.profile_type}
                onValueChange={(value: ProfileType) =>
                  setProfile({ ...profile, profile_type: value })
                }
                className='flex flex-row space-x-4'
              >
                <div className='flex items-center space-x-2'>
                  <RadioGroupItem
                    value='text'
                    id='text'
                  />
                  <Label htmlFor='text'>{t('profiles.string')}</Label>
                </div>
                <div className='flex items-center space-x-2'>
                  <RadioGroupItem
                    value='option'
                    id='option'
                  />
                  <Label htmlFor='option'>{t('profiles.option')}</Label>
                </div>
              </RadioGroup>
            </div>
          </div>

          {profile.profile_type === 'option' && (
            <>
              <div className='grid grid-cols-4 gap-4'>
                <div className='col-span-4'>
                  <Label className='mb-2 block'>{t('profiles.enumItem')}</Label>
                  {!!profile.profile_items?.length && (
                    <div className='mb-3 rounded-md border'>
                      <div className='grid grid-cols-12 border-b bg-muted px-3 py-2 text-sm font-medium'>
                        <div className='col-span-5'>
                          {t('profiles.optionValue')}
                        </div>
                        <div className='col-span-5'>
                          {t('profiles.optionName')}
                        </div>
                        <div className='col-span-2 text-right'>
                          {t('profiles.operation')}
                        </div>
                      </div>
                      <div className='divide-y'>
                        {(profile.profile_items || []).map((item, index) => (
                          <div
                            key={`${item.value}-${index}`}
                            className='grid grid-cols-12 items-center px-3 py-2'
                          >
                            <div className='col-span-5 truncate'>
                              {item.value}
                            </div>
                            <div className='col-span-5 truncate'>
                              {item.name}
                            </div>
                            <div className='col-span-2 text-right'>
                              <Button
                                variant='ghost'
                                size='icon'
                                className='h-7 w-7'
                                onClick={() => handleRemoveEnumItem(index)}
                              >
                                <X className='h-4 w-4' />
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className='grid grid-cols-12 gap-2'>
                    <Input
                      placeholder={t('profiles.optionValue')}
                      value={newEnumItem.value}
                      onChange={e =>
                        setNewEnumItem({
                          ...newEnumItem,
                          value: e.target.value,
                        })
                      }
                      className='col-span-5'
                    />
                    <Input
                      placeholder={t('profiles.title')}
                      value={newEnumItem.name}
                      onChange={e =>
                        setNewEnumItem({
                          ...newEnumItem,
                          name: e.target.value,
                        })
                      }
                      className='col-span-5'
                    />
                    <Button
                      onClick={handleAddEnumItem}
                      className='col-span-2 h-8'
                      disabled={
                        !newEnumItem.value.trim() || !newEnumItem.name.trim()
                      }
                    >
                      {t('profiles.add')}
                    </Button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
        <DialogFooter>
          <Button
            className='h-8'
            variant='outline'
            onClick={handleCancelSaveProfile}
          >
            {t('profiles.cancel')}
          </Button>
          <Button
            className='h-8'
            onClick={handleSaveProfile}
            disabled={
              !profile.profile_key.trim() ||
              (profile.profile_type === 'option' &&
                (profile.profile_items || []).length === 0)
            }
          >
            {isEditing ? t('profiles.save') : t('profiles.add')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
export default ProfileSave;
