import { useShifu } from "@/store"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select"
import { cn } from "@/lib/utils";
import { useTranslation } from 'react-i18next';

export default function ModelList({ value, className, onChange }: { value: string, className?: string, onChange: (value: string) => void }) {
    const { models } = useShifu();
    const { t } = useTranslation();
    return (
        <Select
            onValueChange={onChange}
            value={value || ''}
        >
            <SelectTrigger className={cn("w-full", className)}>
                <SelectValue />
            </SelectTrigger>
            <SelectContent>
                <SelectItem value="">{t('common.default')}</SelectItem>
                {
                    models.map((item, i) => {
                        return <SelectItem key={i} value={item}>{item}</SelectItem>
                    })
                }
            </SelectContent>
        </Select>
    )
}
