'use client';

import React from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useForm } from 'react-hook-form';
import api from '@/api';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import Loading from '@/components/loading';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/Form';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
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
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/Popover';
import { cn } from '@/lib/utils';
import { ChevronDown } from 'lucide-react';
import type { Shifu } from '@/types/shifu';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';

interface ImportActivationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (orderBid: string) => void;
}

interface ImportActivationEntry {
  mobile: string;
  nickname: string;
}

const MAX_BULK_MOBILE_COUNT = 50;
const MOBILE_SAMPLE_LIMIT = 5;
const MAX_IMPORT_TEXT_LENGTH = 10000;
const TEXT_CHAR_PATTERN = /[A-Za-z\u4E00-\u9FFF]/;
const PHONE_MATCH_PATTERN = /(?:^|\D)(\d{11})(?!\d)/g;
const PHONE_TEST_PATTERN = /(?:^|\D)\d{11}(?!\d)/;
const EMAIL_TEST_PATTERN =
  /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;
const EMAIL_ALLOWED_CHARS = new Set(
  'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._%+-'.split(''),
);

const trimNickname = (value: string): string => {
  const text = value.trim();
  if (!text) {
    return '';
  }
  let start = 0;
  let end = text.length;
  while (start < end && !TEXT_CHAR_PATTERN.test(text[start])) {
    start += 1;
  }
  while (end > start && !TEXT_CHAR_PATTERN.test(text[end - 1])) {
    end -= 1;
  }
  return text.slice(start, end).trim();
};

const trimDisplayLine = (value: string): string => {
  return value.replace(/^[\s,，、]+|[\s,，、]+$/g, '');
};

const findPhoneMatches = (
  value: string,
): Array<{ index: number; value: string }> => {
  const matches: Array<{ index: number; value: string }> = [];
  const pattern = new RegExp(PHONE_MATCH_PATTERN.source, 'g');
  let match = pattern.exec(value);
  while (match) {
    const raw = match[0];
    const digits = match[1];
    if (digits) {
      const start = (match.index ?? 0) + raw.length - digits.length;
      matches.push({ index: start, value: digits });
    }
    match = pattern.exec(value);
  }
  return matches;
};

const findEmailMatches = (
  value: string,
): Array<{ index: number; value: string }> => {
  if (!value.includes('@')) {
    return [];
  }
  const matches: Array<{ index: number; value: string }> = [];
  const seen = new Set<string>();
  for (let index = 0; index < value.length; index += 1) {
    if (value[index] !== '@') {
      continue;
    }
    let left = index - 1;
    while (left >= 0 && EMAIL_ALLOWED_CHARS.has(value[left])) {
      left -= 1;
    }
    let right = index + 1;
    while (right < value.length && EMAIL_ALLOWED_CHARS.has(value[right])) {
      right += 1;
    }
    const start = left + 1;
    const end = right;
    if (end - start <= 3) {
      continue;
    }
    const candidate = value.slice(start, end);
    if (!EMAIL_TEST_PATTERN.test(candidate)) {
      continue;
    }
    const key = `${start}:${end}`;
    if (seen.has(key)) {
      continue;
    }
    matches.push({ index: start, value: candidate });
    seen.add(key);
  }
  matches.sort((a, b) => a.index - b.index);
  return matches;
};

const hasValidIdentifier = (
  line: string,
  contactType: 'phone' | 'email',
): boolean => {
  if (!line) {
    return false;
  }
  if (contactType === 'email') {
    return findEmailMatches(line).length > 0;
  }
  return PHONE_TEST_PATTERN.test(line);
};

const parseImportText = (
  value: string,
  contactType: 'phone' | 'email',
): {
  entries: ImportActivationEntry[];
  normalizedText: string;
  invalidItems: string[];
} => {
  const safeValue = value.slice(0, MAX_IMPORT_TEXT_LENGTH);
  const invalidItems = safeValue
    .split(/\r?\n/)
    .map(line => trimDisplayLine(line))
    .filter(
      item => item.length > 0 && !hasValidIdentifier(item, contactType),
    );
  const matches =
    contactType === 'email'
      ? findEmailMatches(safeValue)
      : findPhoneMatches(safeValue);
  if (matches.length === 0) {
    return { entries: [], normalizedText: safeValue, invalidItems };
  }

  const entries = matches.map((match, index) => {
    const start = match.index;
    const end =
      index + 1 < matches.length
        ? matches[index + 1].index
        : safeValue.length;
    const segment = safeValue.slice(start, end);
    const identifier =
      contactType === 'email' ? match.value.toLowerCase() : match.value;
    const nicknameSource = segment.replace(match.value, '');
    const nickname = trimNickname(nicknameSource);
    return { mobile: identifier, nickname };
  });

  const displayLines = matches.map((match, index) => {
    const start = match.index;
    const end =
      index + 1 < matches.length
        ? matches[index + 1].index
        : safeValue.length;
    const segment = safeValue.slice(start, end);
    return trimDisplayLine(segment);
  });

  return {
    entries,
    normalizedText: displayLines.join('\n'),
    invalidItems,
  };
};

const ImportActivationDialog = ({
  open,
  onOpenChange,
  onSuccess,
}: ImportActivationDialogProps) => {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const loginMethodsEnabled = useEnvStore(
    (state: EnvStoreState) => state.loginMethodsEnabled,
  );
  const defaultLoginMethod = useEnvStore(
    (state: EnvStoreState) => state.defaultLoginMethod,
  );
  const [courses, setCourses] = React.useState<Shifu[]>([]);
  const [coursesLoading, setCoursesLoading] = React.useState(false);
  const [coursesError, setCoursesError] = React.useState<string | null>(null);
  const [courseSearch, setCourseSearch] = React.useState('');
  const [courseOpen, setCourseOpen] = React.useState(false);
  const dialogContentRef = React.useRef<HTMLDivElement | null>(null);
  const contactType = React.useMemo(
    () => resolveContactMode(loginMethodsEnabled, defaultLoginMethod),
    [defaultLoginMethod, loginMethodsEnabled],
  );
  const isEmailMode = contactType === 'email';
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [pendingIdentifiers, setPendingIdentifiers] = React.useState<string[]>(
    [],
  );
  const [pendingEntries, setPendingEntries] = React.useState<
    ImportActivationEntry[]
  >([]);
  const [isImporting, setIsImporting] = React.useState(false);
  const isImportingRef = React.useRef(false);
  const listSeparator = React.useMemo(
    () => (i18n.language?.startsWith('zh') ? '，' : ', '),
    [i18n.language],
  );
  const joinedIdentifiers = React.useMemo(() => {
    return pendingIdentifiers.join(listSeparator);
  }, [listSeparator, pendingIdentifiers]);
  const contactLabel = isEmailMode
    ? t('module.order.importActivation.emailLabel')
    : t('module.order.importActivation.mobileLabel');
  const contactPlaceholder = isEmailMode
    ? t('module.order.importActivation.emailPlaceholder')
    : t('module.order.importActivation.mobilePlaceholder');
  const contactRequiredMessage = isEmailMode
    ? t('module.order.importActivation.emailRequired')
    : t('module.order.importActivation.mobileRequired');
  const contactConfirmTitle = isEmailMode
    ? t('module.order.importActivation.emailConfirmTitle')
    : t('module.order.importActivation.confirmTitle');
  const buildInvalidMessage = React.useCallback(
    (values: string) =>
      isEmailMode
        ? t('module.order.importActivation.emailInvalidLines', { values })
        : t('module.order.importActivation.mobileInvalidLines', { values }),
    [isEmailMode, t],
  );
  const buildDuplicateMessage = React.useCallback(
    (numbers: string) =>
      isEmailMode
        ? t('module.order.importActivation.emailDuplicate', { numbers })
        : t('module.order.importActivation.mobileDuplicate', { numbers }),
    [isEmailMode, t],
  );
  const buildLimitMessage = React.useCallback(
    (count: number) =>
      isEmailMode
        ? t('module.order.importActivation.emailLimit', { count })
        : t('module.order.importActivation.mobileLimit', { count }),
    [isEmailMode, t],
  );
  const buildSuccessSummary = React.useCallback(
    (count: number) =>
      isEmailMode
        ? t('module.order.importActivation.emailSuccessSummary', { count })
        : t('module.order.importActivation.successSummary', { count }),
    [isEmailMode, t],
  );

  const formSchema = React.useMemo(
    () =>
      z.object({
        mobile: z.string().trim().min(1, contactRequiredMessage),
        course_id: z
          .string()
          .trim()
          .min(1, t('module.order.importActivation.courseRequired')),
        user_nick_name: z.string().optional(),
      }),
    [contactRequiredMessage, t],
  );

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      mobile: '',
      course_id: '',
      user_nick_name: '',
    },
  });

  const courseNameMap = React.useMemo(() => {
    const map = new Map<string, string>();
    courses.forEach(course => {
      if (!course.bid) {
        return;
      }
      map.set(course.bid, course.name || course.bid);
    });
    return map;
  }, [courses]);

  const confirmText = React.useMemo(
    () =>
      isEmailMode
        ? t('module.order.importActivation.emailConfirmDescription', {
            mobiles: joinedIdentifiers,
            count: pendingIdentifiers.length,
          })
        : t('module.order.importActivation.confirmDescription', {
            mobiles: joinedIdentifiers,
            count: pendingIdentifiers.length,
          }),
    [isEmailMode, joinedIdentifiers, pendingIdentifiers.length, t],
  );

  const filteredCourses = React.useMemo(() => {
    const keyword = courseSearch.trim().toLowerCase();
    if (!keyword) {
      return courses;
    }
    return courses.filter(course => {
      const name = (course.name || '').toLowerCase();
      const bid = (course.bid || '').toLowerCase();
      const matchesName = name.includes(keyword);
      const matchesBid = Boolean(bid && bid === keyword);
      return matchesName || matchesBid;
    });
  }, [courseSearch, courses]);

  const normalizeContactField = React.useCallback(
    (value: string) => {
      const { entries, normalizedText, invalidItems } = parseImportText(
        value,
        contactType,
      );
      if (
        invalidItems.length === 0 &&
        entries.length > 0 &&
        normalizedText &&
        normalizedText !== value
      ) {
        form.setValue('mobile', normalizedText, {
          shouldDirty: true,
          shouldTouch: true,
        });
      }
    },
    [contactType, form],
  );

  const handleSubmit = async (values: z.infer<typeof formSchema>) => {
    const mobileInput = values.mobile || '';
    const { entries, normalizedText, invalidItems } = parseImportText(
      mobileInput,
      contactType,
    );
    if (invalidItems.length > 0) {
      const sample = invalidItems
        .slice(0, MOBILE_SAMPLE_LIMIT)
        .join(listSeparator);
      const displayValues =
        invalidItems.length > MOBILE_SAMPLE_LIMIT ? `${sample}...` : sample;
      form.setError('mobile', {
        message: buildInvalidMessage(displayValues),
      });
      return;
    }
    if (entries.length === 0) {
      form.setError('mobile', {
        message: contactRequiredMessage,
      });
      return;
    }
    if (entries.length > MAX_BULK_MOBILE_COUNT) {
      form.setError('mobile', {
        message: buildLimitMessage(MAX_BULK_MOBILE_COUNT),
      });
      return;
    }

    if (normalizedText && normalizedText !== mobileInput) {
      form.setValue('mobile', normalizedText, {
        shouldDirty: true,
        shouldTouch: true,
      });
    }

    const fallbackNickname = values.user_nick_name?.trim() || '';
    const entriesForPayload = entries.map(entry => {
      if (!fallbackNickname) {
        return entry;
      }
      const hasNickname =
        typeof entry.nickname === 'string' && entry.nickname.trim().length > 0;
      if (hasNickname) {
        return entry;
      }
      return { ...entry, nickname: fallbackNickname };
    });

    const mobiles = entriesForPayload.map(entry => entry.mobile);
    const uniqueKeys = mobiles.map(mobile =>
      contactType === 'email' ? mobile.toLowerCase() : mobile,
    );
    const duplicateMobiles = Array.from(
      new Set(
        uniqueKeys.filter((mobile, idx) => uniqueKeys.indexOf(mobile) !== idx),
      ),
    );
    if (duplicateMobiles.length > 0) {
      const sample = duplicateMobiles
        .slice(0, MOBILE_SAMPLE_LIMIT)
        .join(listSeparator);
      const messageMobiles =
        duplicateMobiles.length > MOBILE_SAMPLE_LIMIT ? `${sample}...` : sample;
      form.setError('mobile', {
        message: buildDuplicateMessage(messageMobiles),
      });
      return;
    }

    setPendingEntries(entriesForPayload);
    setPendingIdentifiers(mobiles);
    setConfirmOpen(true);
  };

  const handleConfirmImport = async (
    entries: ImportActivationEntry[],
    values: z.infer<typeof formSchema>,
  ) => {
    if (isImportingRef.current) {
      return;
    }
    isImportingRef.current = true;
    setIsImporting(true);
    const lines = entries.map(entry =>
      entry.nickname ? `${entry.mobile} ${entry.nickname}` : entry.mobile,
    );
    const payload = {
      lines,
      course_id: values.course_id.trim(),
      contact_type: contactType,
    };

    try {
      const response = (await api.importActivationOrder(payload)) as {
        success?: { mobile: string; order_bid?: string }[];
        failed?: { mobile: string; message?: string }[];
      };
      const successCount = response?.success?.length ?? 0;
      const failedCount = response?.failed?.length ?? 0;
      const failedEntries = response?.failed ?? [];
      const totalCount = entries.length;

      if (failedCount === 0) {
        toast({
          title: t('module.order.importActivation.success'),
          description: buildSuccessSummary(successCount),
        });
        onSuccess?.('');
        onOpenChange(false);
        return;
      }

      const courseNotFoundMessage = t(
        'server.shifu.courseNotFound',
        'Course not found',
      )
        .trim()
        .toLowerCase();
      const isCourseError =
        successCount === 0 &&
        failedCount === totalCount &&
        failedEntries.length > 0 &&
        failedEntries.every(entry => {
          const msg = entry.message?.toLowerCase() || '';
          return courseNotFoundMessage
            ? msg.includes(courseNotFoundMessage)
            : false;
        });
      if (isCourseError) {
        toast({
          title:
            failedEntries[0]?.message ||
            t('module.order.importActivation.failed'),
          variant: 'destructive',
        });
        return;
      }

      const failedMessage = response?.failed
        ?.slice(0, 5)
        .map(item =>
          item.message ? `${item.mobile}: ${item.message}` : item.mobile,
        )
        .join('\n');

      toast({
        title: t('module.order.importActivation.partialSummary', {
          successCount,
          failedCount,
        }),
        description: failedMessage,
        variant: successCount > 0 ? 'default' : 'destructive',
      });
      if (successCount > 0) {
        onSuccess?.('');
      }
    } catch (error) {
      let message = t('module.order.importActivation.failed');
      if (error instanceof ErrorWithCode) {
        message = error.message;
      } else if (error instanceof Error) {
        message = error.message;
      }
      toast({
        title: message,
        variant: 'destructive',
      });
    } finally {
      setIsImporting(false);
      isImportingRef.current = false;
    }
  };

  React.useEffect(() => {
    if (open) {
      form.reset();
      form.clearErrors();
      return;
    }
    setConfirmOpen(false);
    setPendingIdentifiers([]);
    setPendingEntries([]);
    setIsImporting(false);
    isImportingRef.current = false;
  }, [open, form]);

  React.useEffect(() => {
    if (!courseOpen) {
      setCourseSearch('');
    }
  }, [courseOpen]);

  React.useEffect(() => {
    if (!open) {
      setCourseSearch('');
      setCourseOpen(false);
      return;
    }

    let canceled = false;
    const loadCourses = async () => {
      setCoursesLoading(true);
      setCoursesError(null);
      try {
        const pageSize = 100;
        let pageIndex = 1;
        const collected: Shifu[] = [];
        const seen = new Set<string>();

        while (true) {
          const { items } = await api.getAdminOrderShifus({
            page_index: pageIndex,
            page_size: pageSize,
            published: true,
          });
          const pageItems = (items || []) as Shifu[];
          pageItems.forEach(item => {
            if (item?.bid && !seen.has(item.bid)) {
              seen.add(item.bid);
              collected.push(item);
            }
          });
          if (pageItems.length < pageSize) {
            break;
          }
          pageIndex += 1;
        }

        if (!canceled) {
          setCourses(collected);
        }
      } catch {
        if (!canceled) {
          setCourses([]);
          setCoursesError(t('common.core.networkError'));
        }
      } finally {
        if (!canceled) {
          setCoursesLoading(false);
        }
      }
    };

    loadCourses();

    return () => {
      canceled = true;
    };
  }, [open, t]);

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={onOpenChange}
      >
        <DialogContent ref={dialogContentRef}>
          <DialogHeader>
            <DialogTitle>
              {t('module.order.importActivation.title')}
            </DialogTitle>
            <DialogDescription>
              {t('module.order.importActivation.description')}
            </DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(handleSubmit)}
              className='space-y-4'
            >
              <FormField
                control={form.control}
                name='mobile'
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{contactLabel}</FormLabel>
                    <FormControl>
                      <Textarea
                        autoComplete='off'
                        placeholder={contactPlaceholder}
                        className='min-h-[80px]'
                        maxLength={MAX_IMPORT_TEXT_LENGTH}
                        {...field}
                        onChange={e => field.onChange(e.target.value)}
                        onBlur={event => {
                          field.onBlur();
                          normalizeContactField(event.target.value);
                        }}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name='course_id'
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      {t('module.order.importActivation.courseLabel')}
                    </FormLabel>
                    <Popover
                      modal={false}
                      open={courseOpen}
                      onOpenChange={setCourseOpen}
                    >
                      <PopoverTrigger asChild>
                        <FormControl>
                          <Button
                            type='button'
                            variant='outline'
                            className='w-full justify-between font-normal'
                            title={
                              field.value
                                ? courseNameMap.get(field.value) || field.value
                                : undefined
                            }
                          >
                            <span
                              className={cn(
                                'flex-1 truncate text-left',
                                field.value
                                  ? 'text-foreground'
                                  : 'text-muted-foreground',
                              )}
                            >
                              {field.value
                                ? courseNameMap.get(field.value) || field.value
                                : t(
                                    'module.order.importActivation.coursePlaceholder',
                                  )}
                            </span>
                            <ChevronDown className='h-4 w-4 text-muted-foreground' />
                          </Button>
                        </FormControl>
                      </PopoverTrigger>
                      <PopoverContent
                        align='start'
                        sideOffset={4}
                        container={dialogContentRef.current ?? undefined}
                        className='z-50 p-3 pointer-events-auto'
                        style={{
                          width: 'var(--radix-popover-trigger-width)',
                          maxWidth: 'var(--radix-popover-trigger-width)',
                        }}
                      >
                        <Input
                          value={courseSearch}
                          onChange={event =>
                            setCourseSearch(event.target.value)
                          }
                          placeholder={t(
                            'module.order.filters.searchCourseOrId',
                          )}
                          className='h-8'
                        />
                        <div className='mt-3 max-h-48 overflow-auto'>
                          {coursesLoading ? (
                            <div className='flex items-center justify-center py-4'>
                              <Loading className='h-5 w-5' />
                            </div>
                          ) : coursesError ? (
                            <div className='px-2 py-3 text-xs text-destructive'>
                              {coursesError}
                            </div>
                          ) : filteredCourses.length === 0 ? (
                            <div className='px-2 py-3 text-xs text-muted-foreground'>
                              {t('common.core.noShifus')}
                            </div>
                          ) : (
                            <div className='space-y-1'>
                              {filteredCourses.map(course => {
                                const isSelected = field.value === course.bid;
                                const courseName = course.name || course.bid;
                                return (
                                  <button
                                    key={course.bid}
                                    type='button'
                                    onClick={() => {
                                      field.onChange(course.bid);
                                      setCourseOpen(false);
                                    }}
                                    className='flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent'
                                    aria-pressed={isSelected}
                                  >
                                    <span className='flex flex-col min-w-0'>
                                      <span className='text-sm text-foreground truncate'>
                                        {courseName}
                                      </span>
                                    </span>
                                  </button>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      </PopoverContent>
                    </Popover>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name='user_nick_name'
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      {t('module.order.importActivation.nicknameLabel')}
                    </FormLabel>
                    <FormControl>
                      <Input
                        autoComplete='off'
                        placeholder={t(
                          'module.order.importActivation.nicknamePlaceholder',
                        )}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className='flex justify-end gap-2'>
                <Button
                  type='button'
                  variant='outline'
                  onClick={() => onOpenChange(false)}
                >
                  {t('common.core.cancel')}
                </Button>
                <Button
                  type='submit'
                  disabled={form.formState.isSubmitting || isImporting}
                >
                  {form.formState.isSubmitting || isImporting
                    ? t('module.order.importActivation.submitting')
                    : t('module.order.importActivation.submit')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{contactConfirmTitle}</AlertDialogTitle>
            <AlertDialogDescription className='text-muted-foreground'>
              {confirmText}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              onClick={() => setConfirmOpen(false)}
              disabled={isImporting}
            >
              {t('common.core.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                const currentValues = form.getValues();
                setConfirmOpen(false);
                void handleConfirmImport(pendingEntries, currentValues);
              }}
              disabled={isImporting}
            >
              {t('common.core.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};

export default ImportActivationDialog;
