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
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/Popover';
import { ScrollArea } from '@/components/ui/ScrollArea';
import { cn } from '@/lib/utils';
import { Check, ChevronDown } from 'lucide-react';
import type { Shifu } from '@/types/shifu';

interface ImportActivationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (orderBid: string) => void;
}

const MAX_BULK_MOBILE_COUNT = 50;
const MOBILE_PATTERN = /^\d{11}$/;
const MOBILE_SAMPLE_LIMIT = 5;

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

  const formSchema = React.useMemo(
    () =>
      z.object({
        mobile: z
          .string()
          .trim()
          .min(1, t('module.order.importActivation.mobileRequired')),
        course_id: z
          .string()
          .trim()
          .min(1, t('module.order.importActivation.courseRequired')),
        user_nick_name: z.string().optional(),
      }),
    [t],
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

  const parseMobiles = React.useCallback((value: string) => {
    return value
      .split(/[,，\n]/)
      .map(item => item.trim())
      .filter(Boolean);
  }, []);

  const handleSubmit = async (values: z.infer<typeof formSchema>) => {
    const mobileInput = values.mobile || '';
    const mobiles = parseMobiles(mobileInput);
    if (mobiles.length === 0) {
      form.setError('mobile', {
        message: t('module.order.importActivation.mobileRequired'),
      });
      return;
    }
    if (mobiles.length > MAX_BULK_MOBILE_COUNT) {
      form.setError('mobile', {
        message: t('module.order.importActivation.mobileLimit', {
          count: MAX_BULK_MOBILE_COUNT,
        }),
      });
      return;
    }

    const invalidMobiles = mobiles.filter(
      mobile => !MOBILE_PATTERN.test(mobile),
    );
    if (invalidMobiles.length > 0) {
      const sample = invalidMobiles
        .slice(0, MOBILE_SAMPLE_LIMIT)
        .join(', ');
      const messageMobiles =
        invalidMobiles.length > MOBILE_SAMPLE_LIMIT ? `${sample}...` : sample;
      form.setError('mobile', {
        message: t('module.order.importActivation.mobileInvalid', {
          numbers: messageMobiles,
        }),
      });
      return;
    }

    const payload = {
      mobile: mobiles.join(','),
      course_id: values.course_id.trim(),
      user_nick_name: values.user_nick_name?.trim() || undefined,
    };

    try {
      const response = (await api.importActivationOrder(payload)) as {
        success?: { mobile: string; order_bid?: string }[];
        failed?: { mobile: string; message?: string }[];
      };
      const successCount = response?.success?.length ?? 0;
      const failedCount = response?.failed?.length ?? 0;
      const failedEntries = response?.failed ?? [];

      if (failedCount === 0) {
        toast({
          title: t('module.order.importActivation.success'),
          description: t('module.order.importActivation.successSummary', {
            count: successCount,
          }),
        });
        onSuccess?.('');
        onOpenChange(false);
        return;
      }

      const isCourseError =
        successCount === 0 &&
        failedCount === mobiles.length &&
        failedEntries.length > 0 &&
        failedEntries.every(entry => {
          const msg = entry.message?.toLowerCase() || '';
          return (
            msg.includes('课程不存在') || msg.includes('course not found')
          );
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
          const { items } = await api.getShifuList({
            page_index: pageIndex,
            page_size: pageSize,
            is_favorite: false,
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
      } catch (error) {
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
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent ref={dialogContentRef}>
        <DialogHeader>
          <DialogTitle>{t('module.order.importActivation.title')}</DialogTitle>
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
                  <FormLabel>
                    {t('module.order.importActivation.mobileLabel')}
                  </FormLabel>
                  <FormControl>
                    <Textarea
                      autoComplete='off'
                      placeholder={t(
                        'module.order.importActivation.mobilePlaceholder',
                      )}
                      className='min-h-[80px]'
                      {...field}
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
                        onChange={event => setCourseSearch(event.target.value)}
                        placeholder={t('module.order.filters.searchCourseOrId')}
                        className='h-8'
                      />
                      <ScrollArea className='mt-3 h-48'>
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
                      </ScrollArea>
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
  );
};

export default ImportActivationDialog;
