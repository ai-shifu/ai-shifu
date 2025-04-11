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

const formSchema = z.object({
    scenario_name: z.string()
        .min(1, "请输入剧本名称")
        .max(20, "剧本名称不能超过20个字符"),
    scenario_description: z.string()
        .min(1, "请输入剧本描述")
        .max(500, "剧本描述不能超过500个字符"),
    scenario_image: z.string().default(""),
});

interface CreateScenarioDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSubmit: (values: z.infer<typeof formSchema>) => Promise<void>;
}

export const CreateScenarioDialog = ({
    open,
    onOpenChange,
    onSubmit
}: CreateScenarioDialogProps) => {
    const form = useForm<z.infer<typeof formSchema>>({
        resolver: zodResolver(formSchema),
        defaultValues: {
            scenario_name: "",
            scenario_description: "",
            scenario_image: "",
        },
    });

    const handleSubmit = async (values: z.infer<typeof formSchema>) => {
        await onSubmit(values);
        form.reset();
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
                    <DialogTitle>新建空白剧本</DialogTitle>
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
                                    >剧本名称</FormLabel>
                                    <FormControl>
                                        <Input autoComplete='off' placeholder="请输入剧本名称" {...field} />
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
                                    >剧本描述</FormLabel>
                                    <FormControl>
                                        <Textarea autoComplete='off' placeholder="请输入剧本描述" {...field} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <div className="flex justify-end">
                            <Button type="submit" disabled={form.formState.isSubmitting}>
                                {form.formState.isSubmitting ? "创建中..." : "创建"}
                            </Button>
                        </div>
                    </form>
                </Form>
            </DialogContent>
        </Dialog>
    );
};
