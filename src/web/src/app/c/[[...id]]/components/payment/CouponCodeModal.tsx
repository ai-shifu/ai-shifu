'use client';
import styles from './CouponCodeModal.module.scss';

import { useCallback, memo } from 'react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';

import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/Form';

import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';

export const CouponCodeModal = ({ open = false, onCancel, onOk }) => {
  const { t } = useTranslation();

  const formSchema = z.object({
    couponCode: z.string().min(1, {
      message: t('module.groupon.inputMessage'),
    }),
  });

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      couponCode: '',
    },
  });

  const _onOk = useCallback(
    async (values: z.infer<typeof formSchema>) => {
      try {
        await onOk?.(values);
      } catch {
        // errors handled by request layer toasts
      }
    },
    [onOk],
  );

  function handleOpenChange(open) {
    if (!open) {
      onCancel?.();
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={handleOpenChange}
    >
      <Form {...form}>
        <form
          id='coupon-code-form'
          onSubmit={form.handleSubmit(_onOk)}
        >
          <DialogContent
            className={cn(styles.couponCodeModal, 'w-96')}
            onPointerDownOutside={evt => evt.preventDefault()}
          >
            <DialogHeader>
              <DialogTitle>{t('module.groupon.title')}</DialogTitle>
            </DialogHeader>

            <FormField
              control={form.control}
              name='couponCode'
              render={({ field }) => (
                <FormItem>
                  <FormControl>
                    <Input
                      placeholder={t('module.groupon.placeholder')}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type='button'
                onClick={() => form.handleSubmit(_onOk)()}
                form='coupon-code-form'
              >
                {t('common.core.ok')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </form>
      </Form>
    </Dialog>
  );
};

export default memo(CouponCodeModal);
