'use client';

import React from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useForm } from 'react-hook-form';
import api from '@/api';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
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
                  <FormControl>
                    <Input
                      autoComplete='off'
                      placeholder={t(
                        'module.order.importActivation.coursePlaceholder',
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
