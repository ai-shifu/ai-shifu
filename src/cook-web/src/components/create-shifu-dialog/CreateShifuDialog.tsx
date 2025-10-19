import React from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useForm } from 'react-hook-form';
import {
  Dialog,
  DialogContent,
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
import { useTranslation } from 'react-i18next';

interface FormSchema {
  shifu_name: string;
  shifu_description: string;
  shifu_image: string;
}
interface CreateShifuDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (values: FormSchema) => Promise<void>;
}
export const CreateShifuDialog = ({
  open,
  onOpenChange,
  onSubmit,
}: CreateShifuDialogProps) => {
  const { t } = useTranslation();

  const formSchema = z.object({
    name: z
      .string()
      .min(1, t('component.createShifuDialog.nameRequired'))
      .max(20, t('component.createShifuDialog.nameMaxLength')),
    description: z
      .string()
      .max(500, t('component.createShifuDialog.descriptionMaxLength'))
      .optional(),
    avatar: z.string().default(''),
  });

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: '',
      description: '',
      avatar: '',
    },
  });

  const handleSubmit = async values => {
    await onSubmit(values);
    // form.reset();
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
          <DialogTitle>{t('component.createShifuDialog.title')}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(handleSubmit)}
            className='space-y-4'
          >
            <FormField
              control={form.control}
              name='name'
              render={({ field }) => (
                <FormItem>
                  <FormLabel
                    style={{
                      color: '#000000',
                    }}
                  >
                    {t('component.createShifuDialog.nameLabel')}
                  </FormLabel>
                  <FormControl>
                    <Input
                      autoComplete='off'
                      placeholder={t(
                        'component.createShifuDialog.namePlaceholder',
                      )}
                      {...field}
                      maxLength={20}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name='description'
              render={({ field }) => (
                <FormItem>
                  <FormLabel
                    style={{
                      color: '#000000',
                    }}
                  >
                    {t('component.createShifuDialog.descriptionLabel')}
                  </FormLabel>
                  <FormControl>
                    <Textarea
                      autoComplete='off'
                      placeholder={t(
                        'component.createShifuDialog.descriptionPlaceholder',
                      )}
                      {...field}
                      maxLength={300}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className='flex justify-end'>
              <Button
                type='submit'
                disabled={form.formState.isSubmitting}
              >
                {form.formState.isSubmitting
                  ? t('component.createShifuDialog.creating')
                  : t('component.createShifuDialog.create')}
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateShifuDialog;
