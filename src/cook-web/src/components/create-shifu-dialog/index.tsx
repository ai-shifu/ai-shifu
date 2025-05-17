import React from 'react';
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useForm } from "react-hook-form";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    Form,
    FormControl,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
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
    onSubmit
}: CreateShifuDialogProps) => {
    const { t } = useTranslation();

    const formSchema = z.object({
        shifu_name: z.string()
            .min(1, t('create-shifu-dialog.shifu-name-cannot-be-empty'))
            .max(20, t('create-shifu-dialog.shifu-name-cannot-exceed-20-characters')),
        shifu_description: z.string()
            .max(500, t('create-shifu-dialog.shifu-description-cannot-exceed-500-characters'))
            .optional(),
        shifu_image: z.string().default(""),
    });

    const form = useForm<z.infer<typeof formSchema>>({
        resolver: zodResolver(formSchema),
        defaultValues: {
            shifu_name: "",
            shifu_description: "",
            shifu_image: "",
        },
    });

    const handleSubmit = async (values) => {
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
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>{t('create-shifu-dialog.create-blank-shifu')}</DialogTitle>
                </DialogHeader>
                <Form {...form}>
                    <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
                        <FormField
                            control={form.control}
                            name="shifu_name"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel
                                        style={{
                                            color: "#000000"
                                        }}
                                    >{t('create-shifu-dialog.shifu-name')}</FormLabel>
                                    <FormControl>
                                        <Input autoComplete='off' placeholder={t('create-shifu-dialog.please-input-shifu-name')} {...field} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <FormField
                            control={form.control}
                            name="shifu_description"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel
                                        style={{
                                            color: "#000000"
                                        }}
                                    >{t('create-shifu-dialog.shifu-description')}</FormLabel>
                                    <FormControl>
                                        <Textarea autoComplete='off' placeholder={t('create-shifu-dialog.please-input-shifu-description')} {...field} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <div className="flex justify-end">
                            <Button type="submit" disabled={form.formState.isSubmitting}>
                                {form.formState.isSubmitting ? t('create-shifu-dialog.creating') : t('create-shifu-dialog.create')}
                            </Button>
                        </div>
                    </form>
                </Form>
            </DialogContent>
        </Dialog>
    );
};
