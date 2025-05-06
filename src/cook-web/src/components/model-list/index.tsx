import { useScenario } from "@/store"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select"
import { cn } from "@/lib/utils";
import { useTranslation } from 'react-i18next';

/**
 * Renders a dropdown select component for choosing a model from the available list.
 *
 * The list of models is retrieved from the current scenario context. The placeholder and labels are internationalized using the translation hook.
 *
 * @param value - The currently selected model.
 * @param className - Optional additional CSS classes for the select trigger.
 * @param onChange - Callback invoked when the selected model changes.
 */
export default function ModelList({ value, className, onChange }: { value: string, className?: string, onChange: (value: string) => void }) {
    const { models } = useScenario();
    const { t } = useTranslation();
    return (
        <Select
            onValueChange={onChange}
            defaultValue={value}
        >
            <SelectTrigger className={cn("w-full", className)}>
                <SelectValue placeholder={t('model-list.select-model')} />
            </SelectTrigger>
            <SelectContent>
                {
                    models.map((item, i) => {
                        return <SelectItem key={i} value={item}>{item}</SelectItem>
                    })
                }
            </SelectContent>
        </Select>
    )
}
