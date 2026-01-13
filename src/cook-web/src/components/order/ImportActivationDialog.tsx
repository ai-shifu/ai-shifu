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
      return name.includes(keyword) || bid.includes(keyword);
    });
  }, [courseSearch, courses]);

  const handleSubmit = async (values: z.infer<typeof formSchema>) => {
    const payload = {
      mobile: values.mobile.trim(),
      course_id: values.course_id.trim(),
      user_nick_name: values.user_nick_name?.trim() || undefined,
    };

    try {
      const response = (await api.importActivationOrder(payload)) as {
        order_bid?: string;
      };
      toast({
        title: t('module.order.importActivation.success'),
      });
      onSuccess?.(response?.order_bid || '');
      onOpenChange(false);
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
      <DialogContent>
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
                    <Input
                      autoComplete='off'
                      placeholder={t(
                        'module.order.importActivation.mobilePlaceholder',
                      )}
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
                    <PopoverContent className='w-[--radix-popover-trigger-width] p-3'>
                      <Input
                        value={courseSearch}
                        onChange={event => setCourseSearch(event.target.value)}
                        placeholder={t('module.order.filters.search')}
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
                                  <span
                                    className={cn(
                                      'mt-0.5 flex h-4 w-4 items-center justify-center rounded border',
                                      isSelected
                                        ? 'border-primary bg-primary text-primary-foreground'
                                        : 'border-muted-foreground/40 text-transparent',
                                    )}
                                  >
                                    <Check className='h-3 w-3' />
                                  </span>
                                  <span className='flex flex-col'>
                                    <span className='text-sm text-foreground'>
                                      {courseName}
                                    </span>
                                    <span className='text-xs text-muted-foreground'>
                                      {course.bid}
                                    </span>
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
