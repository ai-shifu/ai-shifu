'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import api from '@/api';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { useToast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
import type {
  AdminOperationUserItem,
  AdminOperationUserListResponse,
} from '../operation-user-types';

const TEACHER_SEARCH_PAGE_SIZE = 10;

type VoiceCloneRegisterDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRegistered: () => void;
};

const formatTeacherContact = (teacher: AdminOperationUserItem) =>
  [teacher.mobile, teacher.email].filter(Boolean).join(' / ');

export default function VoiceCloneRegisterDialog({
  open,
  onOpenChange,
  onRegistered,
}: VoiceCloneRegisterDialogProps) {
  const { t } = useTranslation();
  const { toast } = useToast();

  const [teacherKeyword, setTeacherKeyword] = React.useState('');
  const [searching, setSearching] = React.useState(false);
  const [searchResults, setSearchResults] = React.useState<
    AdminOperationUserItem[]
  >([]);
  const [searched, setSearched] = React.useState(false);
  const [selectedTeacher, setSelectedTeacher] =
    React.useState<AdminOperationUserItem | null>(null);
  const [displayName, setDisplayName] = React.useState('');
  const [voiceId, setVoiceId] = React.useState('');
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState('');

  const resetState = React.useCallback(() => {
    setTeacherKeyword('');
    setSearching(false);
    setSearchResults([]);
    setSearched(false);
    setSelectedTeacher(null);
    setDisplayName('');
    setVoiceId('');
    setSubmitting(false);
    setError('');
  }, []);

  React.useEffect(() => {
    if (!open) {
      resetState();
    }
  }, [open, resetState]);

  const handleSearchTeacher = React.useCallback(async () => {
    const keyword = teacherKeyword.trim();
    if (!keyword || searching) {
      return;
    }
    setSearching(true);
    setError('');
    try {
      const response = (await api.getAdminOperationUsers({
        page_index: 1,
        page_size: TEACHER_SEARCH_PAGE_SIZE,
        identifier: keyword,
      })) as AdminOperationUserListResponse;
      setSearchResults(Array.isArray(response.items) ? response.items : []);
      setSearched(true);
    } catch (caughtError) {
      const typedError = caughtError as Partial<ErrorWithCode>;
      setError(typedError.message || t('common.core.networkError'));
      setSearchResults([]);
      setSearched(true);
    } finally {
      setSearching(false);
    }
  }, [searching, t, teacherKeyword]);

  const handleSubmit = React.useCallback(async () => {
    if (submitting) {
      return;
    }
    if (!selectedTeacher) {
      setError(t('module.operationsVoiceClone.register.teacherRequired'));
      return;
    }
    if (!displayName.trim()) {
      setError(t('module.operationsVoiceClone.register.displayNameRequired'));
      return;
    }
    if (!voiceId.trim()) {
      setError(t('module.operationsVoiceClone.register.voiceIdRequired'));
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await api.registerAdminOperationVoiceClone({
        owner_user_bid: selectedTeacher.user_bid,
        display_name: displayName.trim(),
        voice_id: voiceId.trim(),
      });
      toast({
        title: t('module.operationsVoiceClone.register.successToast'),
      });
      onOpenChange(false);
      onRegistered();
    } catch (caughtError) {
      const typedError = caughtError as Partial<ErrorWithCode>;
      setError(typedError.message || t('common.core.networkError'));
    } finally {
      setSubmitting(false);
    }
  }, [
    displayName,
    onOpenChange,
    onRegistered,
    selectedTeacher,
    submitting,
    t,
    toast,
    voiceId,
  ]);

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className='sm:max-w-[520px]'>
        <DialogHeader>
          <DialogTitle>
            {t('module.operationsVoiceClone.register.title')}
          </DialogTitle>
          <DialogDescription>
            {t('module.operationsVoiceClone.register.description')}
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4 py-2'>
          <div className='space-y-2'>
            <Label>
              {t('module.operationsVoiceClone.register.teacherLabel')}
            </Label>
            {selectedTeacher ? (
              <div className='flex items-center justify-between gap-2 rounded-md border px-3 py-2'>
                <div className='min-w-0'>
                  <p className='truncate text-sm font-medium'>
                    {selectedTeacher.nickname ||
                      formatTeacherContact(selectedTeacher) ||
                      selectedTeacher.user_bid}
                  </p>
                  <p className='truncate text-xs text-muted-foreground'>
                    {formatTeacherContact(selectedTeacher)}
                  </p>
                </div>
                <Button
                  type='button'
                  variant='ghost'
                  size='sm'
                  onClick={() => setSelectedTeacher(null)}
                >
                  {t('module.operationsVoiceClone.register.clearTeacher')}
                </Button>
              </div>
            ) : (
              <>
                <div className='flex gap-2'>
                  <Input
                    value={teacherKeyword}
                    onChange={event => setTeacherKeyword(event.target.value)}
                    onKeyDown={event => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        void handleSearchTeacher();
                      }
                    }}
                    placeholder={t(
                      'module.operationsVoiceClone.register.teacherSearchPlaceholder',
                    )}
                    className='h-9 flex-1'
                  />
                  <Button
                    type='button'
                    variant='outline'
                    size='sm'
                    onClick={() => void handleSearchTeacher()}
                    disabled={searching || !teacherKeyword.trim()}
                  >
                    {searching
                      ? t('module.operationsVoiceClone.register.searching')
                      : t('module.operationsVoiceClone.register.searchButton')}
                  </Button>
                </div>
                {searched && searchResults.length === 0 && !searching ? (
                  <p className='text-xs text-muted-foreground'>
                    {t('module.operationsVoiceClone.register.noResults')}
                  </p>
                ) : null}
                {searchResults.length > 0 ? (
                  <div className='max-h-48 space-y-1 overflow-auto rounded-md border p-1'>
                    {searchResults.map(teacher => (
                      <button
                        key={teacher.user_bid}
                        type='button'
                        onClick={() => {
                          setSelectedTeacher(teacher);
                          setError('');
                        }}
                        className='flex w-full flex-col items-start rounded-md px-2 py-1.5 text-left hover:bg-muted'
                      >
                        <span className='truncate text-sm font-medium'>
                          {teacher.nickname ||
                            formatTeacherContact(teacher) ||
                            teacher.user_bid}
                        </span>
                        <span className='truncate text-xs text-muted-foreground'>
                          {formatTeacherContact(teacher)}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </>
            )}
          </div>

          <div className='space-y-2'>
            <Label htmlFor='voice-clone-display-name'>
              {t('module.operationsVoiceClone.register.displayNameLabel')}
            </Label>
            <Input
              id='voice-clone-display-name'
              value={displayName}
              onChange={event => setDisplayName(event.target.value)}
              placeholder={t(
                'module.operationsVoiceClone.register.displayNamePlaceholder',
              )}
              className='h-9'
            />
          </div>

          <div className='space-y-2'>
            <Label htmlFor='voice-clone-voice-id'>
              {t('module.operationsVoiceClone.register.voiceIdLabel')}
            </Label>
            <Input
              id='voice-clone-voice-id'
              value={voiceId}
              onChange={event => setVoiceId(event.target.value)}
              placeholder={t(
                'module.operationsVoiceClone.register.voiceIdPlaceholder',
              )}
              className='h-9'
            />
            <p className='text-xs text-muted-foreground'>
              {t('module.operationsVoiceClone.register.voiceIdHint')}
            </p>
          </div>

          {error ? (
            <div className='rounded-md border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive'>
              {error}
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button
            type='button'
            variant='outline'
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            {t('module.operationsVoiceClone.register.cancel')}
          </Button>
          <Button
            type='button'
            onClick={() => void handleSubmit()}
            disabled={submitting}
          >
            {submitting
              ? t('module.operationsVoiceClone.register.submitting')
              : t('module.operationsVoiceClone.register.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
