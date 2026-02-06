'use client';

import React from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useForm } from 'react-hook-form';
import api from '@/api';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
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
const TEXT_CHAR_PATTERN = /[A-Za-z\u4E00-\u9FFF]/;
const PHONE_MATCH_PATTERN = /\d{11}/g;
const PHONE_TEST_PATTERN = /\d{11}/;
const EMAIL_MATCH_PATTERN = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const EMAIL_TEST_PATTERN = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/;

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

const parseImportText = (
  value: string,
  contactType: 'phone' | 'email',
): {
  entries: ImportActivationEntry[];
  normalizedText: string;
  invalidItems: string[];
} => {
  const testPattern =
    contactType === 'email' ? EMAIL_TEST_PATTERN : PHONE_TEST_PATTERN;
  const invalidItems = value
    .split(/\r?\n/)
    .map(line => trimDisplayLine(line))
    .filter(item => item.length > 0 && !testPattern.test(item));
  const matchPattern =
    contactType === 'email' ? EMAIL_MATCH_PATTERN : PHONE_MATCH_PATTERN;
  const matches = Array.from(
    value.matchAll(new RegExp(matchPattern.source, 'g')),
  );
  if (matches.length === 0) {
    return { entries: [], normalizedText: value, invalidItems };
  }

  const entries = matches.map((match, index) => {
    const start = match.index ?? 0;
    const end =
      index + 1 < matches.length
        ? (matches[index + 1].index ?? value.length)
        : value.length;
    const segment = value.slice(start, end);
    const identifier =
      contactType === 'email' ? match[0].toLowerCase() : match[0];
    const nicknameSource = segment.replace(match[0], '');
    const nickname = trimNickname(nicknameSource);
    return { mobile: identifier, nickname };
  });

  const displayLines = matches.map((match, index) => {
    const start = match.index ?? 0;
    const end =
      index + 1 < matches.length
        ? (matches[index + 1].index ?? value.length)
        : value.length;
    const segment = value.slice(start, end);
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
  const { t } = useTranslation();
  const { toast } = useToast();
  const [courses, setCourses] = React.useState<Shifu[]>([]);
  const [coursesLoading, setCoursesLoading] = React.useState(false);
  const [coursesError, setCoursesError] = React.useState<string | null>(null);
  const [courseSearch, setCourseSearch] = React.useState('');
  const [courseOpen, setCourseOpen] = React.useState(false);
  const dialogContentRef = React.useRef<HTMLDivElement | null>(null);
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [pendingMobiles, setPendingMobiles] = React.useState<string[]>([]);
  const [pendingEntries, setPendingEntries] = React.useState<
    ImportActivationEntry[]
  >([]);
  const joinedIdentifiers = React.useMemo(
    () => pendingMobiles.join('，'),
    [pendingMobiles],
  );
  const isEmailMode = React.useMemo(
    () =>
      typeof window !== 'undefined' &&
      window.location.hostname.endsWith('.com'),
    [],
  );
  const contactType = isEmailMode ? 'email' : 'phone';
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
            count: pendingMobiles.length,
          })
        : t('module.order.importActivation.confirmDescription', {
            mobiles: joinedIdentifiers,
            count: pendingMobiles.length,
          }),
    [isEmailMode, joinedIdentifiers, pendingMobiles.length, t],
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

  const normalizeMobileField = React.useCallback(
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
      const sample = invalidItems.slice(0, MOBILE_SAMPLE_LIMIT).join('，');
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
    const hasLineNickname = entries.some(entry => entry.nickname);
    const entriesForPayload =
      fallbackNickname && !hasLineNickname
        ? entries.map(entry => ({
            ...entry,
            nickname: fallbackNickname,
          }))
        : entries;

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
      const sample = duplicateMobiles.slice(0, MOBILE_SAMPLE_LIMIT).join(', ');
      const messageMobiles =
        duplicateMobiles.length > MOBILE_SAMPLE_LIMIT ? `${sample}...` : sample;
      form.setError('mobile', {
        message: buildDuplicateMessage(messageMobiles),
      });
      return;
    }

    setPendingEntries(entriesForPayload);
    setPendingMobiles(mobiles);
    setConfirmOpen(true);
  };

  const handleConfirmImport = async (
    entries: ImportActivationEntry[],
    values: z.infer<typeof formSchema>,
  ) => {
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

      const isCourseError =
        successCount === 0 &&
        failedCount === totalCount &&
        failedEntries.length > 0 &&
        failedEntries.every(entry => {
          const msg = entry.message?.toLowerCase() || '';
          return msg.includes('课程不存在') || msg.includes('course not found');
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
    }
  };

  React.useEffect(() => {
    if (open) {
      form.reset();
      form.clearErrors();
    }
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
                        {...field}
                        onChange={e => field.onChange(e.target.value)}
                        onBlur={event => {
                          field.onBlur();
                          normalizeMobileField(event.target.value);
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
                                      {/* <span className='text-xs text-muted-foreground'>
                                        {course.bid}
                                      </span> */}
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
                  disabled={form.formState.isSubmitting}
                >
                  {form.formState.isSubmitting
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
            <AlertDialogCancel onClick={() => setConfirmOpen(false)}>
              {t('common.core.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                const currentValues = form.getValues();
                setConfirmOpen(false);
                void handleConfirmImport(pendingEntries, currentValues);
              }}
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
