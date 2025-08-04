'use client';

import type React from 'react';

import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/Dialog';
import { Plus } from 'lucide-react';
import ProfileSelect from './ProfileSelect';
import type { Profile } from '@/components/profiles/types';
import { useTranslation } from 'react-i18next';

interface ProfileSelectModalProps {
  isDialogOpen: boolean;
  setIsDialogOpen: React.Dispatch<React.SetStateAction<boolean>>;
  onAddProfile: (profile: Profile) => void;
}

export default function ProfileSelectModal({
  isDialogOpen,
  setIsDialogOpen,
  onAddProfile,
}: ProfileSelectModalProps) {
  const { t } = useTranslation();
  const handleProfileSelect = (profile: Profile) => {
    onAddProfile(profile);
  };
  return (
    <Dialog
      open={isDialogOpen}
      onOpenChange={setIsDialogOpen}
    >
      <DialogTrigger asChild>
        <Button
          variant={'outline'}
          size='sm'
          className='h-8'
        >
          <Plus className='h-4 w-4 mr-1' />
          {t('profile-select-modal.add')}
        </Button>
      </DialogTrigger>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{t('profile-select-modal.add-variable')}</DialogTitle>
        </DialogHeader>
        <div className='space-y-4 pt-4'>
          <ProfileSelect onSelect={handleProfileSelect} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
