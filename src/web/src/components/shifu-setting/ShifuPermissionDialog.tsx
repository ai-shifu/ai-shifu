import React from 'react';
import { Check, ChevronDown } from 'lucide-react';
import useSWR from 'swr';
import { Trans, useTranslation } from 'react-i18next';
import api from '@/api';
import { useEnvStore } from '@/c-store';
import { useUserStore } from '@/store';
import { useToast } from '@/hooks/useToast';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import { isValidEmail } from '@/lib/validators';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/Button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/AlertDialog';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import { Label } from '@/components/ui/Label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/RadioGroup';
import { ScrollArea } from '@/components/ui/ScrollArea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { Textarea } from '@/components/ui/Textarea';

type SharedPermission = {
  user_id: string;
  identifier: string;
  nickname?: string;
  permission: 'view' | 'edit' | 'publish';
};

type PermissionDialogShifu = {
  bid: string;
  created_user_bid?: string;
} | null;

type ShifuPermissionDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  shifu: PermissionDialogShifu;
};

const MAX_SHARED_PERMISSION_COUNT = 10;
const INVALID_CONTACT_SAMPLE_LIMIT = 5;
const PERMISSION_PHONE_PATTERN = /^\d{11}$/;
const PHONE_EXTRACT_PATTERN = /(?:^|\D)(\d{11})(?!\d)/g;
const PHONE_TOKEN_PATTERN = /\d{11}/;
const PHONE_TOKEN_SPLIT_PATTERN = /[\s,;\n\uFF0C\uFF1B]+/;
const EMAIL_EXTRACT_PATTERN = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const EMAIL_CANDIDATE_PATTERN = /[^\s,\uFF0C;\uFF1B]+@[^\s,\uFF0C;\uFF1B]+/g;

const unique = (items: string[]): string[] => Array.from(new Set(items));

const normalizeEmailCandidate = (value: string): string =>
  value.replace(/^[,\uFF0C;\uFF1B.\u3002]+|[,\uFF0C;\uFF1B.\u3002]+$/g, '');

export default function ShifuPermissionDialog({
  open,
  onOpenChange,
  shifu,
}: ShifuPermissionDialogProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const currentUser = useUserStore(state => state.userInfo);
  const currentUserId = currentUser?.user_id || '';
  const loginMethodsEnabled = useEnvStore(state => state.loginMethodsEnabled);
  const defaultLoginMethod = useEnvStore(state => state.defaultLoginMethod);
  const contactType = React.useMemo(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );
  const canManagePermissions =
    Boolean(shifu?.created_user_bid) &&
    shifu?.created_user_bid === currentUserId;

  const [permissionInput, setPermissionInput] = React.useState('');
  const [permissionError, setPermissionError] = React.useState('');
  const [permissionLevel, setPermissionLevel] =
    React.useState<SharedPermission['permission']>('view');
  const [grantLoading, setGrantLoading] = React.useState(false);
  const [grantConfirmOpen, setGrantConfirmOpen] = React.useState(false);
  const [pendingGrantContacts, setPendingGrantContacts] = React.useState<
    string[]
  >([]);
  const [pendingGrantPermission, setPendingGrantPermission] =
    React.useState<SharedPermission['permission']>('view');
  const [permissionEditMode, setPermissionEditMode] = React.useState(false);
  const [permissionEdits, setPermissionEdits] = React.useState<
    Record<string, SharedPermission['permission']>
  >({});
  const [permissionRemovals, setPermissionRemovals] = React.useState<
    Set<string>
  >(new Set());
  const [permissionConfirmOpen, setPermissionConfirmOpen] =
    React.useState(false);
  const [permissionSaveLoading, setPermissionSaveLoading] =
    React.useState(false);

  const resetState = React.useCallback(() => {
    setPermissionError('');
    setPermissionInput('');
    setPermissionEditMode(false);
    setPermissionEdits({});
    setPermissionRemovals(new Set());
    setGrantConfirmOpen(false);
    setPermissionConfirmOpen(false);
    setPendingGrantContacts([]);
    setPendingGrantPermission('view');
    setPermissionLevel('view');
    setGrantLoading(false);
    setPermissionSaveLoading(false);
  }, []);

  React.useEffect(() => {
    if (!open) {
      resetState();
    }
  }, [open, resetState]);

  React.useEffect(() => {
    resetState();
  }, [resetState, shifu?.bid]);

  const permissionKey = React.useMemo(() => {
    if (!open || !shifu?.bid || !canManagePermissions) {
      return null;
    }
    return ['shifu-permissions', shifu.bid, contactType] as const;
  }, [canManagePermissions, contactType, open, shifu?.bid]);

  const {
    data: permissionData,
    error: permissionLoadError,
    isLoading: permissionLoading,
    mutate: refreshPermissionList,
  } = useSWR(
    permissionKey,
    async ([, shifuBid, contactTypeValue]) =>
      (await api.listShifuPermissions({
        shifu_bid: shifuBid,
        contact_type: contactTypeValue,
      })) as { items?: SharedPermission[] },
    { revalidateOnFocus: false },
  );

  const permissionList = React.useMemo(
    () => permissionData?.items || [],
    [permissionData],
  );

  React.useEffect(() => {
    if (!permissionLoadError || !open) {
      return;
    }
    const message =
      permissionLoadError instanceof Error
        ? permissionLoadError.message
        : t('common.core.unknownError');
    toast({ title: message, variant: 'destructive' });
  }, [open, permissionLoadError, t, toast]);

  const contactLabel =
    contactType === 'email'
      ? t('module.shifuSetting.permissionEmailLabel')
      : t('module.shifuSetting.permissionPhoneLabel');
  const contactPlaceholder =
    contactType === 'email'
      ? t('module.shifuSetting.permissionEmailPlaceholder')
      : t('module.shifuSetting.permissionPhonePlaceholder');

  const permissionOptions = React.useMemo(
    () => [
      { value: 'view', label: t('module.shifuSetting.permissionReadOnly') },
      { value: 'edit', label: t('module.shifuSetting.permissionEdit') },
      { value: 'publish', label: t('module.shifuSetting.permissionPublish') },
    ],
    [t],
  );

  const parseContacts = React.useCallback(
    (value: string) => {
      if (!value.trim()) {
        return { contacts: [], invalidContacts: [] };
      }

      if (contactType === 'phone') {
        const matches = Array.from(value.matchAll(PHONE_EXTRACT_PATTERN)).map(
          match => match[1],
        );
        const contacts = unique(matches).filter(phone =>
          PERMISSION_PHONE_PATTERN.test(phone),
        );
        const tokens = value
          .split(PHONE_TOKEN_SPLIT_PATTERN)
          .filter(token => token.length > 0);
        const invalidContacts = unique(
          tokens
            .filter(
              token => /\d/.test(token) && !PHONE_TOKEN_PATTERN.test(token),
            )
            .map(token => token.replace(/\D/g, ''))
            .filter(
              candidate =>
                candidate.length > 0 &&
                !PERMISSION_PHONE_PATTERN.test(candidate),
            ),
        );
        return { contacts, invalidContacts };
      }

      const emailMatches = Array.from(
        value.matchAll(EMAIL_EXTRACT_PATTERN),
      ).map(match => match[0].toLowerCase());
      const contacts = unique(emailMatches);
      const candidateMatches = Array.from(
        value.matchAll(EMAIL_CANDIDATE_PATTERN),
      ).map(match => normalizeEmailCandidate(match[0]).toLowerCase());
      const invalidContacts = unique(candidateMatches).filter(
        candidate => candidate && !isValidEmail(candidate),
      );
      return { contacts, invalidContacts };
    },
    [contactType],
  );

  const handleGrantPermissions = React.useCallback(async () => {
    if (!shifu?.bid || !canManagePermissions) {
      return;
    }
    const { contacts, invalidContacts } = parseContacts(permissionInput);
    if (invalidContacts.length > 0) {
      const sample = invalidContacts
        .slice(0, INVALID_CONTACT_SAMPLE_LIMIT)
        .join(', ');
      const messageContacts =
        invalidContacts.length > INVALID_CONTACT_SAMPLE_LIMIT
          ? `${sample}...`
          : sample;
      setPermissionError(
        contactType === 'email'
          ? t('module.shifuSetting.permissionEmailInvalid', {
              values: messageContacts,
            })
          : t('module.shifuSetting.permissionPhoneInvalid', {
              values: messageContacts,
            }),
      );
      return;
    }
    if (contacts.length === 0) {
      setPermissionError(t('module.shifuSetting.permissionContactRequired'));
      return;
    }
    const normalizedExisting = new Set(
      permissionList.map(item =>
        contactType === 'email'
          ? (item.identifier || '').toLowerCase()
          : item.identifier || '',
      ),
    );
    const normalizedContacts = contacts.map(contact =>
      contactType === 'email' ? contact.toLowerCase() : contact,
    );
    const ownerEmail =
      typeof currentUser?.email === 'string'
        ? currentUser.email.toLowerCase()
        : '';
    const ownerPhoneCandidate =
      typeof currentUser?.phone === 'string'
        ? currentUser.phone
        : typeof currentUser?.mobile === 'string'
          ? currentUser.mobile
          : typeof currentUser?.user_mobile === 'string'
            ? currentUser.user_mobile
            : '';
    const ownerPhone = ownerPhoneCandidate.replace(/\D/g, '');
    const ownerContact = contactType === 'email' ? ownerEmail : ownerPhone;
    if (ownerContact && normalizedContacts.includes(ownerContact)) {
      setPermissionError(t('module.shifuSetting.permissionOwnerNotAllowed'));
      return;
    }
    const existingContacts = contacts.filter((contact, index) =>
      normalizedExisting.has(normalizedContacts[index]),
    );
    const newContacts = contacts.filter(
      (_contact, index) => !normalizedExisting.has(normalizedContacts[index]),
    );

    if (existingContacts.length > 0) {
      const sample = existingContacts
        .slice(0, INVALID_CONTACT_SAMPLE_LIMIT)
        .join(', ');
      const messageContacts =
        existingContacts.length > INVALID_CONTACT_SAMPLE_LIMIT
          ? `${sample}...`
          : sample;
      setPermissionError(
        t('module.shifuSetting.permissionDuplicate', {
          values: messageContacts,
        }),
      );
      return;
    }

    if (
      permissionList.length + newContacts.length >
      MAX_SHARED_PERMISSION_COUNT
    ) {
      setPermissionError(
        t('module.shifuSetting.permissionLimit', {
          count: MAX_SHARED_PERMISSION_COUNT,
        }),
      );
      return;
    }

    setPermissionError('');
    setPendingGrantContacts(newContacts);
    setPendingGrantPermission(permissionLevel);
    setGrantConfirmOpen(true);
  }, [
    canManagePermissions,
    contactType,
    currentUser,
    parseContacts,
    permissionInput,
    permissionLevel,
    permissionList,
    shifu?.bid,
    t,
  ]);

  const handleConfirmGrantPermissions = React.useCallback(async () => {
    if (
      !shifu?.bid ||
      !canManagePermissions ||
      pendingGrantContacts.length === 0
    ) {
      setGrantConfirmOpen(false);
      return;
    }
    setPermissionError('');
    setGrantLoading(true);
    try {
      await api.grantShifuPermissions({
        shifu_bid: shifu.bid,
        contact_type: contactType,
        contacts: pendingGrantContacts,
        permission: pendingGrantPermission,
      });
      toast({ title: t('module.shifuSetting.permissionGrantSuccess') });
      await refreshPermissionList();
      onOpenChange(false);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t('common.core.unknownError');
      toast({ title: message, variant: 'destructive' });
    } finally {
      setGrantLoading(false);
    }
  }, [
    canManagePermissions,
    contactType,
    onOpenChange,
    pendingGrantContacts,
    pendingGrantPermission,
    refreshPermissionList,
    shifu?.bid,
    t,
    toast,
  ]);

  const pendingGrantPermissionLabel = React.useMemo(() => {
    const match = permissionOptions.find(
      option => option.value === pendingGrantPermission,
    );
    return match?.label || pendingGrantPermission;
  }, [pendingGrantPermission, permissionOptions]);

  const handleUpdatePermission = React.useCallback(
    (
      item: SharedPermission,
      nextPermission: SharedPermission['permission'],
    ) => {
      if (item.permission === nextPermission) {
        setPermissionEdits(prev => {
          if (!(item.user_id in prev)) {
            return prev;
          }
          const next = { ...prev };
          delete next[item.user_id];
          return next;
        });
        return;
      }
      setPermissionEdits(prev => ({
        ...prev,
        [item.user_id]: nextPermission,
      }));
    },
    [],
  );

  const handleSavePermissionChanges = React.useCallback(async () => {
    if (!shifu?.bid || !canManagePermissions) {
      return;
    }
    const removalIds = Array.from(permissionRemovals);
    const updates = Object.entries(permissionEdits).filter(
      ([userId]) => !permissionRemovals.has(userId),
    );
    if (removalIds.length === 0 && updates.length === 0) {
      toast({
        title: t('module.shifuSetting.permissionEditNoChanges'),
      });
      return;
    }
    setPermissionSaveLoading(true);
    try {
      type PermissionOperation = {
        type: 'remove' | 'grant';
        userId: string;
        permission?: SharedPermission['permission'];
        identifier?: string;
      };

      const removalOperations: PermissionOperation[] = removalIds.map(
        userId => ({
          type: 'remove' as const,
          userId,
        }),
      );
      const grantOperations: PermissionOperation[] = updates.map(
        ([userId, nextPermission]) => {
          const item = permissionList.find(entry => entry.user_id === userId);
          return {
            type: 'grant' as const,
            userId,
            permission: nextPermission,
            identifier: item?.identifier || '',
          };
        },
      );
      const operations = [...removalOperations, ...grantOperations];

      const missingIdentifiers = operations.filter(
        operation => operation.type === 'grant' && !operation.identifier,
      );
      if (missingIdentifiers.length > 0) {
        throw new Error(t('module.shifuSetting.permissionContactRequired'));
      }

      const removals = operations.filter(
        operation => operation.type === 'remove',
      );
      const grants = operations.filter(operation => operation.type === 'grant');

      const removalResults = await Promise.allSettled(
        removals.map(operation =>
          api.removeShifuPermission({
            shifu_bid: shifu.bid,
            user_id: operation.userId,
          }),
        ),
      );
      const grantResults = await Promise.allSettled(
        grants.map(operation =>
          api.grantShifuPermissions({
            shifu_bid: shifu.bid,
            contact_type: contactType,
            contacts: [operation.identifier || ''],
            permission: operation.permission || 'view',
          }),
        ),
      );
      const results = [...removalResults, ...grantResults];

      const failed = results
        .map((result, index) => ({
          result,
          operation: [...removals, ...grants][index],
        }))
        .filter(item => item.result.status === 'rejected')
        .map(item => item.operation.identifier || item.operation.userId);

      await refreshPermissionList();
      setPermissionConfirmOpen(false);

      if (failed.length > 0) {
        setPermissionEdits({});
        setPermissionRemovals(new Set());
        toast({
          title: t('common.core.unknownError'),
          description: failed.join(', '),
          variant: 'destructive',
        });
        return;
      }

      toast({ title: t('module.shifuSetting.permissionEditSuccess') });
      setPermissionEditMode(false);
      setPermissionEdits({});
      setPermissionRemovals(new Set());
      onOpenChange(false);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t('common.core.unknownError');
      toast({ title: message, variant: 'destructive' });
    } finally {
      setPermissionSaveLoading(false);
    }
  }, [
    canManagePermissions,
    contactType,
    onOpenChange,
    permissionEdits,
    permissionList,
    permissionRemovals,
    refreshPermissionList,
    shifu?.bid,
    t,
    toast,
  ]);

  const permissionLabelMap = React.useMemo(() => {
    return permissionOptions.reduce<Record<string, string>>((map, option) => {
      map[option.value] = option.label;
      return map;
    }, {});
  }, [permissionOptions]);

  const permissionOriginalMap = React.useMemo(() => {
    const map = new Map<string, SharedPermission['permission']>();
    permissionList.forEach(item => {
      map.set(item.user_id, item.permission);
    });
    return map;
  }, [permissionList]);

  const sortedPermissionList = React.useMemo(() => {
    const orderMap: Record<SharedPermission['permission'], number> = {
      view: 0,
      edit: 1,
      publish: 2,
    };
    return [...permissionList].sort((a, b) => {
      const orderDiff = orderMap[a.permission] - orderMap[b.permission];
      if (orderDiff !== 0) {
        return orderDiff;
      }
      const aValue = (a.identifier || a.user_id || '').toLowerCase();
      const bValue = (b.identifier || b.user_id || '').toLowerCase();
      return aValue.localeCompare(bValue);
    });
  }, [permissionList]);

  const permissionChangeSummary = React.useMemo(() => {
    return Object.entries(permissionEdits)
      .filter(([userId]) => !permissionRemovals.has(userId))
      .map(([userId, nextPermission]) => {
        const originalPermission = permissionOriginalMap.get(userId) || 'view';
        const label = permissionLabelMap[nextPermission] || nextPermission;
        const originalLabel =
          permissionLabelMap[originalPermission] || originalPermission;
        const item = permissionList.find(entry => entry.user_id === userId);
        return {
          userId,
          identifier: item?.identifier || item?.user_id || userId,
          from: originalLabel,
          to: label,
        };
      });
  }, [
    permissionEdits,
    permissionLabelMap,
    permissionList,
    permissionOriginalMap,
    permissionRemovals,
  ]);

  const permissionRemovalSummary = React.useMemo(() => {
    return permissionList
      .filter(item => permissionRemovals.has(item.user_id))
      .map(item => ({
        userId: item.user_id,
        identifier: item.identifier || item.user_id,
      }));
  }, [permissionList, permissionRemovals]);

  if (!canManagePermissions || !shifu?.bid) {
    return null;
  }

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={onOpenChange}
      >
        <DialogContent className='pb-4'>
          <DialogHeader>
            <DialogTitle>
              <span>{t('module.shifuSetting.permissionDialogTitle')}</span>
            </DialogTitle>
          </DialogHeader>
          <Tabs
            defaultValue='grant'
            className='w-full'
          >
            <TabsList className='mb-1 w-full justify-start bg-transparent p-0'>
              <TabsTrigger
                value='grant'
                className='rounded-none border-b-2 border-transparent px-0 pb-2 pt-0 data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none'
              >
                {t('module.shifuSetting.permissionTabGrant')}
              </TabsTrigger>
              <TabsTrigger
                value='list'
                className='ml-6 rounded-none border-b-2 border-transparent px-0 pb-2 pt-0 data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none'
              >
                {t('module.shifuSetting.permissionTabList')}
              </TabsTrigger>
            </TabsList>
            <TabsContent
              value='grant'
              className='mt-1 min-h-[256px]'
            >
              <div className='space-y-6'>
                <div className='space-y-4'>
                  <Label className='text-sm font-medium text-foreground'>
                    {contactLabel}
                  </Label>
                  <Textarea
                    value={permissionInput}
                    onChange={event => {
                      setPermissionInput(event.target.value);
                      if (permissionError) {
                        setPermissionError('');
                      }
                    }}
                    placeholder={contactPlaceholder}
                    rows={3}
                  />
                  {permissionError ? (
                    <p className='text-xs text-destructive'>
                      {permissionError}
                    </p>
                  ) : null}
                </div>
                <div className='space-y-4'>
                  <Label className='text-sm font-medium text-foreground'>
                    {t('module.shifuSetting.permissionLabel')}
                  </Label>
                  <RadioGroup
                    value={permissionLevel}
                    onValueChange={value =>
                      setPermissionLevel(
                        value as SharedPermission['permission'],
                      )
                    }
                    className='flex flex-row flex-wrap gap-x-8 gap-y-2'
                  >
                    {permissionOptions.map(option => (
                      <div
                        key={option.value}
                        className='flex items-center'
                      >
                        <RadioGroupItem
                          value={option.value}
                          id={`permission-${option.value}`}
                        />
                        <Label
                          htmlFor={`permission-${option.value}`}
                          className='ml-2 text-sm font-medium text-foreground'
                        >
                          {option.value === 'publish' ? (
                            <>
                              {option.label}
                              <span className='text-xs text-muted-foreground'>
                                {t(
                                  'module.shifuSetting.permissionPublishHintWrapped',
                                  {
                                    hint: t(
                                      'module.shifuSetting.permissionPublishHint',
                                    ),
                                  },
                                )}
                              </span>
                            </>
                          ) : (
                            option.label
                          )}
                        </Label>
                      </div>
                    ))}
                  </RadioGroup>
                </div>
              </div>
              <DialogFooter className='mt-8 gap-2'>
                <Button
                  type='button'
                  variant='outline'
                  onClick={() => onOpenChange(false)}
                  disabled={grantLoading}
                >
                  {t('common.core.cancel')}
                </Button>
                <Button
                  type='button'
                  onClick={handleGrantPermissions}
                  disabled={grantLoading}
                >
                  {grantLoading
                    ? t('common.core.submitting')
                    : t('module.shifuSetting.permissionGrant')}
                </Button>
              </DialogFooter>
            </TabsContent>
            <TabsContent
              value='list'
              className='mt-1 min-h-[256px]'
            >
              <ScrollArea
                type='always'
                className='mt-3 h-[180px] pr-2'
              >
                {permissionLoading ? (
                  <div className='text-xs text-muted-foreground'>
                    {t('module.shifuSetting.permissionLoading')}
                  </div>
                ) : permissionList.length === 0 ? (
                  <div className='text-xs text-muted-foreground'>
                    {t('module.shifuSetting.permissionEmpty')}
                  </div>
                ) : (
                  <div className='space-y-1'>
                    {sortedPermissionList.map(item => (
                      <div
                        key={item.user_id}
                        className='flex items-center gap-3 rounded-md px-2 py-1 hover:bg-muted/40'
                      >
                        <div className='min-w-0 flex-1'>
                          <div className='text-sm font-medium min-w-0'>
                            <span className='relative inline-block max-w-full pr-3'>
                              <span
                                className={cn(
                                  'block truncate',
                                  permissionRemovals.has(item.user_id) &&
                                    'line-through text-muted-foreground',
                                )}
                              >
                                {item.identifier || item.user_id}
                              </span>
                            </span>
                          </div>
                        </div>
                        {!permissionEditMode ? (
                          <div className='flex items-center gap-1 text-xs font-medium text-muted-foreground'>
                            <span>
                              {permissionLabelMap[item.permission] ||
                                item.permission}
                            </span>
                          </div>
                        ) : (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <button
                                type='button'
                                className='flex items-center gap-1 text-xs font-medium text-primary hover:text-primary'
                              >
                                {permissionRemovals.has(item.user_id)
                                  ? t('module.shifuSetting.permissionRemoved')
                                  : permissionLabelMap[
                                      permissionEdits[item.user_id] ||
                                        item.permission
                                    ] ||
                                    permissionEdits[item.user_id] ||
                                    item.permission}
                                <ChevronDown className='h-3.5 w-3.5' />
                              </button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align='end'>
                              {permissionOptions.map(option => (
                                <DropdownMenuItem
                                  key={option.value}
                                  className='justify-between'
                                  onSelect={() => {
                                    if (permissionRemovals.has(item.user_id)) {
                                      setPermissionRemovals(prev => {
                                        const next = new Set(prev);
                                        next.delete(item.user_id);
                                        return next;
                                      });
                                    }
                                    handleUpdatePermission(
                                      item,
                                      option.value as SharedPermission['permission'],
                                    );
                                  }}
                                >
                                  <span>{option.label}</span>
                                  {(permissionEdits[item.user_id] ||
                                    item.permission) === option.value ? (
                                    <Check className='h-4 w-4 text-primary' />
                                  ) : (
                                    <span className='h-4 w-4' />
                                  )}
                                </DropdownMenuItem>
                              ))}
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                className='text-destructive focus:text-destructive'
                                onSelect={() => {
                                  setPermissionRemovals(prev => {
                                    const next = new Set(prev);
                                    if (next.has(item.user_id)) {
                                      next.delete(item.user_id);
                                    } else {
                                      next.add(item.user_id);
                                    }
                                    return next;
                                  });
                                  setPermissionEdits(current => {
                                    if (!(item.user_id in current)) {
                                      return current;
                                    }
                                    const updated = { ...current };
                                    delete updated[item.user_id];
                                    return updated;
                                  });
                                }}
                              >
                                {permissionRemovals.has(item.user_id)
                                  ? t(
                                      'module.shifuSetting.permissionRemoveUndo',
                                    )
                                  : t('module.shifuSetting.permissionRemove')}
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
              {permissionList.length > 0 ? (
                <div className='mt-4 text-xs text-muted-foreground'>
                  {t('module.shifuSetting.permissionCount', {
                    count: permissionList.length,
                    max: MAX_SHARED_PERMISSION_COUNT,
                  })}
                </div>
              ) : null}
              <DialogFooter className='mt-4 gap-2'>
                {permissionEditMode ? (
                  <Button
                    type='button'
                    onClick={() => {
                      const hasChanges =
                        permissionRemovals.size > 0 ||
                        Object.keys(permissionEdits).length > 0;
                      if (!hasChanges) {
                        setPermissionEditMode(false);
                        setPermissionEdits({});
                        setPermissionRemovals(new Set());
                        return;
                      }
                      setPermissionConfirmOpen(true);
                    }}
                  >
                    {t('common.core.confirm')}
                  </Button>
                ) : (
                  <>
                    <Button
                      type='button'
                      variant='outline'
                      onClick={() => onOpenChange(false)}
                    >
                      {t('common.core.cancel')}
                    </Button>
                    <Button
                      type='button'
                      onClick={() => {
                        setPermissionEditMode(true);
                        setPermissionEdits({});
                        setPermissionRemovals(new Set());
                      }}
                    >
                      {t('module.shifuSetting.permissionEdit')}
                    </Button>
                  </>
                )}
              </DialogFooter>
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={grantConfirmOpen}
        onOpenChange={openState => {
          setGrantConfirmOpen(openState);
          if (!openState) {
            setPendingGrantContacts([]);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('module.shifuSetting.permissionGrantConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className='space-y-2 text-sm text-muted-foreground'>
                <div>
                  <Trans
                    i18nKey='module.shifuSetting.permissionGrantConfirmDesc'
                    values={{
                      contactType: contactLabel,
                      permission: pendingGrantPermissionLabel,
                    }}
                    components={{
                      strong: <span className='font-medium text-foreground' />,
                    }}
                  />
                </div>
                <div className='space-y-1'>
                  {pendingGrantContacts.map(contact => (
                    <div key={contact}>{contact}</div>
                  ))}
                </div>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={grantLoading}>
              {t('common.core.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={grantLoading}
              onClick={event => {
                event.preventDefault();
                handleConfirmGrantPermissions();
              }}
            >
              {grantLoading
                ? t('common.core.submitting')
                : t('common.core.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={permissionConfirmOpen}
        onOpenChange={setPermissionConfirmOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('module.shifuSetting.permissionEditConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className='space-y-2 text-sm text-muted-foreground'>
                {permissionChangeSummary.length > 0 ? (
                  <div>
                    <div className='font-medium text-foreground'>
                      {t('module.shifuSetting.permissionEditChangeTitle')}
                    </div>
                    <div className='mt-1 space-y-1'>
                      {permissionChangeSummary.map(item => (
                        <div key={item.userId}>
                          {t('module.shifuSetting.permissionEditChangeItem', {
                            identifier: item.identifier,
                            from: item.from,
                            to: item.to,
                          })}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                {permissionRemovalSummary.length > 0 ? (
                  <div>
                    <div className='font-medium text-foreground'>
                      {t('module.shifuSetting.permissionEditRemoveTitle')}
                    </div>
                    <div className='mt-1 space-y-1'>
                      {permissionRemovalSummary.map(item => (
                        <div key={item.userId}>{item.identifier}</div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={permissionSaveLoading}>
              {t('common.core.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={permissionSaveLoading}
              onClick={event => {
                event.preventDefault();
                handleSavePermissionChanges();
              }}
            >
              {permissionSaveLoading
                ? t('common.core.submitting')
                : t('common.core.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
