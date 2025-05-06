import { useScenario } from "@/store"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select"
import { cn } from "@/lib/utils";
import { useTranslation } from 'react-i18next';

/**
 * Renders a dropdown list of available models for selection.
 *
 * Displays a select input populated with model options retrieved from the scenario context. The placeholder text is internationalized using the translation hook.
 *
 * @param value - The currently selected model value.
 * @param className - Optional additional CSS classes for styling the select trigger.
 * @param onChange - Callback invoked when a different model is selected.
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
