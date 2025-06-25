import styles from './FeedbackModal.module.scss';

import { useCallback, memo } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils'

import { 
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';

import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from "@/components/ui/form"

import { Button } from '@/components/ui/button';
import { Textarea } from "@/components/ui/textarea"

import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from "@hookform/resolvers/zod"

import { submitFeedback } from '@/c-api/bz';
import { toast } from '@/hooks/use-toast';

const FEEDBACK_MAX_LENGTH = 300;

export const FeedbackModal = ({ open, onClose }) => {
  const { t } = useTranslation('translation', { keyPrefix: 'c'});

  const formSchema = z.object({
    feedback: z.string().min(5, {
      message: t('feedback.feedbackPlaceholder'),
    })
  })

  const form =  useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      feedback: '',
    },
  })

  const onSubmitFeedback = useCallback(async (values: z.infer<typeof formSchema>) => {
    try {
      const { feedback } = values;
      await submitFeedback(feedback);

      toast({
        title: t('feedback.feedbackSuccess'),
      })
      onClose();
    } catch {}
  }, [onClose, t]);

  function handleOpenChange(open) {
    if (!open) {
      onClose();
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmitFeedback)}  className={styles.formWrapper}>
            <DialogContent className={styles.feedbackModal}>
              <DialogHeader>
                <DialogTitle className={cn(styles.title)}>
                  {t('feedback.feedbackTitle')}
                </DialogTitle>
              </DialogHeader>

              <FormField
                control={form.control}
                name="feedback"
                render={({ field }) => (
                  <FormItem>
                    <FormControl>
                      <Textarea
                        maxLength={FEEDBACK_MAX_LENGTH}
                        minLength={5}
                        placeholder={t('feedback.feedbackPlaceholder')}
                        className="resize-none h-24"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              
              <DialogFooter>
                  <Button type="submit" className={cn('w-full', styles.okBtn)}>
                     {t('feedback.feedbackSubmit')}
                  </Button>
              </DialogFooter>
            </DialogContent>
          </form>
        </Form>
      </Dialog>
    </>
  );
};

export default memo(FeedbackModal);
