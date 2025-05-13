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
    scenario_name: string;
    scenario_description: string;
    scenario_image: string;
}
interface CreateScenarioDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSubmit: (values: FormSchema) => Promise<void>;
}
export const CreateScenarioDialog = ({
    open,
    onOpenChange,
    onSubmit
}: CreateScenarioDialogProps) => {
    const { t } = useTranslation();

    const formSchema = z.object({
            scenario_name: z.string()
                .min(1, t('create-scenario-dialog.scenario-name-cannot-be-empty'))
                .max(20, t('create-scenario-dialog.scenario-name-cannot-exceed-20-characters')),
            scenario_description: z.string()
                .max(500, t('create-scenario-dialog.scenario-description-cannot-exceed-500-characters'))
            .optional(),
        scenario_image: z.string().default(""),
    });

    const form = useForm<z.infer<typeof formSchema>>({
        resolver: zodResolver(formSchema),
        defaultValues: {
            scenario_name: "",
            scenario_description: "",
            scenario_image: "",
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
                    <DialogTitle>{t('create-scenario-dialog.create-blank-scenario')}</DialogTitle>
                </DialogHeader>
                <Form {...form}>
                    <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
                        <FormField
                            control={form.control}
                            name="scenario_name"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel
                                        style={{
                                            color: "#000000"
                                        }}
                                    >{t('create-scenario-dialog.scenario-name')}</FormLabel>
                                    <FormControl>
                                        <Input autoComplete='off' placeholder={t('create-scenario-dialog.please-input-scenario-name')} {...field} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <FormField
                            control={form.control}
                            name="scenario_description"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel
                                        style={{
                                            color: "#000000"
                                        }}
                                    >{t('create-scenario-dialog.scenario-description')}</FormLabel>
                                    <FormControl>
                                        <Textarea autoComplete='off' placeholder={t('create-scenario-dialog.please-input-scenario-description')} {...field} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <div className="flex justify-end">
                            <Button type="submit" disabled={form.formState.isSubmitting}>
                                {form.formState.isSubmitting ? t('create-scenario-dialog.creating') : t('create-scenario-dialog.create')}
                            </Button>
                        </div>
                    </form>
                </Form>
            </DialogContent>
        </Dialog>
    );
};
