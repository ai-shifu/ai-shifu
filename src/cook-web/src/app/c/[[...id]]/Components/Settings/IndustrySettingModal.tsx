import styles from "./IndustrySettingModal.module.scss";

import { memo } from "react";
import { cn } from '@/lib/utils'

import SettingBaseModal from "./SettingBaseModal";

import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"

import { zodResolver } from "@hookform/resolvers/zod"
import { useForm } from "react-hook-form"
import { z } from "zod"

export const IndustrySettingModal = ({
  open,
  onClose,
  onOk = ({}) => {},
  // initialValues = {},
}) => {
  const formSchema = z.object({
    industry: z.string().min(1, {
      message: '请输入行业',
    }).max(20, {
      message: '长度不能超过20'
    }),
  })

    const form = useForm<z.infer<typeof formSchema>>({
      resolver: zodResolver(formSchema),
      defaultValues: {
        industry: '',
      },
    })

  const onOkClick = async (values: z.infer<typeof formSchema>) => {
    try {
      const { industry } = values;
      onOk?.({ industry });
    } catch {}
  };

  return (
    <SettingBaseModal
      open={open}
      onClose={onClose}
      onOk={onOkClick}
      title='行业'>
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onOkClick)}>
          <FormField
            control={form.control}
            name="industry"
            render={({ field }) => (
              <FormItem>
                <FormControl>
                  <Input placeholder="请输入行业" className={cn(styles.sfInput)} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          /> 
        </form>
      </Form>
    </SettingBaseModal>
  );
};

export default memo(IndustrySettingModal);
