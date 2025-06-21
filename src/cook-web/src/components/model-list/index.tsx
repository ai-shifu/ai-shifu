import { useShifu } from "@/store"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select"
import { cn } from "@/lib/utils";
import { useTranslation } from 'react-i18next';

export default function ModelList({ value, className, onChange }: { value: string, className?: string, onChange: (value: string) => void }) {
    const { models } = useShifu();
    const { t } = useTranslation();

    // Empty string is used to represent using the default model. However, the Select component uses empty string as unselected.
    // So we need to use a special value to represent the empty state in the Select component.
    const EMPTY_VALUE = '__empty__';
    const displayValue = value === '' ? EMPTY_VALUE : value;

    const handleChange = (selectedValue: string) => {
        // If the selected value is the empty value, we need to pass an empty string
        const outputValue = selectedValue === EMPTY_VALUE ? '' : selectedValue;
        onChange(outputValue);
    };

    return (
        <Select
            onValueChange={handleChange}
            value={displayValue}
        >
            <SelectTrigger className={cn("w-full", className)}>
                <SelectValue placeholder={t('common.select-model')} />
            </SelectTrigger>
            <SelectContent>
                <SelectItem key="default" value={EMPTY_VALUE}>{t('common.default')}</SelectItem>
                {
                    models.map((item, i) => {
                        return <SelectItem key={i} value={item}>{item}</SelectItem>
                    })
                }
            </SelectContent>
        </Select>
    )
}
