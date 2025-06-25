import { memo } from 'react';
import { cn } from '@/lib/utils'
import styles from './JobSettingModal.module.scss';
import SettingBaseModal from './SettingBaseModal';

import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from "@/components/ui/form"
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button';

import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from "@hookform/resolvers/zod"

export const JobSettingModal = ({
  open,
  onClose,
  onOk = ({ }) => {},
  initialValues = {},
}) => {
  const formSchema = z.object({
    job: z.string().min(1, {
      message: '请输入职业',
    }).max(20, {
      message: '长度不能超过20',
    })
  })

  const form =  useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      job: initialValues['job'] || '',
    },
  })

  const onOkClick = async (values: z.infer<typeof formSchema>) => {
    try {
      const { job } = values;
      onOk?.({ job });
    } catch {}
  };

  return (
    <SettingBaseModal
      open={open}
      onClose={onClose}
      onOk={onOkClick}
      title="职业"
    >
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onOkClick)}>
          <FormField
            control={form.control}
            name="job"
            render={({ field }) => (
              <FormItem>
                <FormControl>
                  <Input placeholder="请输入职业" className={styles.sfInput} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button type="submit" className={cn('w-full', styles.okBtn)}>
            提交
          </Button>
        </form>
      </Form>
    </SettingBaseModal>
  );
};

export default memo(JobSettingModal);
