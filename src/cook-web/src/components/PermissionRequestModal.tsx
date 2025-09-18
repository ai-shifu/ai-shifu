import { useCallback, memo } from 'react';
import { useTranslation } from 'react-i18next';

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/Dialog';

import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/Form';

import { Button } from '@/components/ui/Button';
import { Textarea } from '@/components/ui/Textarea';

import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';

import { submitFeedback } from '@/c-api/bz';
import { toast } from '@/hooks/useToast';

const REQUEST_MAX_LENGTH = 300;

interface PermissionRequestModalProps {
  open: boolean;
  onClose: () => void;
}

export const PermissionRequestModal = ({
  open,
  onClose,
}: PermissionRequestModalProps) => {
  const { t } = useTranslation('translation', { keyPrefix: 'c' });

  const formSchema = z.object({
    request: z.string().min(5, {
      message: t('permission.requestPlaceholder'),
    }),
  });

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      request: '',
    },
  });

  const onSubmitRequest = useCallback(
    async (values: z.infer<typeof formSchema>) => {
      try {
        const { request } = values;
        // Submit permission request directly (user info is automatically handled by submitFeedback)
        const requestContent = `[权限申请] ${request}`;

        await submitFeedback(requestContent);

        toast({
          title: t('permission.requestSuccess'),
        });
        form.reset();
        onClose();
      } catch (error) {
        console.error('Permission request submission failed:', error);
        toast({
          title: t('permission.requestError'),
          variant: 'destructive',
        });
      }
    },
    [onClose, t, form],
  );

  function handleOpenChange(open: boolean) {
    if (!open) {
      form.reset();
      onClose();
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={handleOpenChange}
    >
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle className='text-center text-lg'>
            {t('permission.requestTitle')}
          </DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmitRequest)}>
            <div className='py-4'>
              <p className='text-sm text-gray-600 mb-4'>
                {t('permission.requestDescription')}
              </p>

              <FormField
                control={form.control}
                name='request'
                render={({ field }) => (
                  <FormItem>
                    <FormControl>
                      <Textarea
                        maxLength={REQUEST_MAX_LENGTH}
                        minLength={5}
                        placeholder={t('permission.requestPlaceholder')}
                        className='resize-none h-24'
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <DialogFooter className='flex justify-between items-center'>
              <Button
                type='button'
                variant='outline'
                onClick={() => handleOpenChange(false)}
                className='min-w-[100px]'
              >
{t('common.cancel')}
              </Button>
              <Button
                type='submit'
                className='min-w-[120px]'
              >
                {t('permission.requestSubmit')}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default memo(PermissionRequestModal);
