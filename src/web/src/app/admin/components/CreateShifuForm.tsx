import { useEffect } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

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
import { TITLE_MAX_LENGTH } from '@/constants/uiConstants';
import {
  buildOnboardingTargetProps,
  ONBOARDING_TARGET_IDS,
} from '@/lib/onboardingTargets';

export interface CreateShifuValues {
  name: string;
  description?: string;
  avatar: string;
}

interface CreateShifuFormProps {
  open: boolean;
  submitting: boolean;
  onSubmit: (values: CreateShifuValues) => Promise<void>;
  onSubmitAttempt: (validateAndCreate: () => Promise<void>) => Promise<void>;
  onInteraction: () => void;
}

export default function CreateShifuForm({
  open,
  submitting,
  onSubmit,
  onSubmitAttempt,
  onInteraction,
}: CreateShifuFormProps) {
  const { t } = useTranslation();
  const formSchema = z.object({
    name: z
      .string()
      .min(1, t('component.createShifuDialog.nameRequired'))
      .max(
        TITLE_MAX_LENGTH,
        t('component.createShifuDialog.nameMaxLength', {
          maxLength: TITLE_MAX_LENGTH,
        }),
      ),
    description: z
      .string()
      .max(500, t('component.createShifuDialog.descriptionMaxLength'))
      .optional(),
    avatar: z.string().default(''),
  });
  const form = useForm<CreateShifuValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { name: '', description: '', avatar: '' },
  });

  useEffect(() => {
    if (open) form.reset();
  }, [open, form]);

  const busy = submitting || form.formState.isSubmitting;

  return (
    <Form {...form}>
      <form
        onChange={onInteraction}
        onSubmit={event => {
          event.preventDefault();
          onInteraction();
          void onSubmitAttempt(() =>
            form.handleSubmit(values => onSubmit(values))(),
          );
        }}
        className='mt-6 flex flex-1 flex-col gap-6'
        aria-busy={busy}
      >
        <fieldset className='min-w-0 flex-1 space-y-5'>
          <FormField
            control={form.control}
            name='name'
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  {t('component.createShifuDialog.nameLabel')}
                </FormLabel>
                <FormControl>
                  <Input
                    autoComplete='off'
                    readOnly={submitting}
                    aria-required='true'
                    placeholder={t(
                      'component.createShifuDialog.namePlaceholder',
                    )}
                    {...field}
                    maxLength={TITLE_MAX_LENGTH}
                    className='h-11 rounded-lg focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
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
                <FormLabel>
                  {t('component.createShifuDialog.descriptionLabel')}
                </FormLabel>
                <FormControl>
                  <Textarea
                    autoComplete='off'
                    readOnly={submitting}
                    placeholder={t(
                      'component.createShifuDialog.descriptionPlaceholder',
                    )}
                    {...field}
                    maxLength={300}
                    rows={4}
                    className='min-h-28 resize-none rounded-lg leading-6 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </fieldset>
        <Button
          type='submit'
          disabled={busy}
          className='h-auto min-h-11 w-full whitespace-normal rounded-lg px-4 py-3 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
          {...buildOnboardingTargetProps(
            ONBOARDING_TARGET_IDS.blankCreateEntry,
          )}
        >
          {busy
            ? t('component.createShifuDialog.creating')
            : t('component.courseCreationChoiceDialog.manualAction')}
        </Button>
      </form>
    </Form>
  );
}
