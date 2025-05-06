import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
  } from "@/components/ui/select"
import { GlobeIcon } from "lucide-react";
import languages from '../../../public/locales/languages.json'
import { useTranslation } from 'react-i18next';
import { useState } from "react";
import i18n from '@/i18n';



type languageProps = {
     variant?: 'circle' | 'standard'
    language?: string
    onSetLanguage?: (value: string) => void
  }





/**
 * Renders a language selection dropdown that allows users to switch the application's language.
 *
 * The component displays a trigger button (with optional circular or standard styling) and a dropdown list of available languages. When a language is selected, it updates the application's language using the i18n instance and optionally calls a provided callback.
 *
 * @param props.variant - Determines the style of the trigger button; either 'circle' or 'standard'.
 * @param props.language - The initial language code to select; defaults to 'zh-CN' if not provided.
 * @param props.onSetLanguage - Optional callback invoked with the new language code when the selection changes.
 */
export default function LanguageSelect(props: languageProps) {
    const { t } = useTranslation();
    // ...其他逻辑
  const triggerClass =
props.variant === 'circle'
    ? 'w-[40px] h-[40px] rounded-full p-0 flex items-center justify-start border-none shadow-none focus:outline-none'
    : 'flex items-center justify-start space-x-2 px-3 py-2 rounded-lg hover:bg-gray-100';

    const [language, setLanguage] = useState(props.language || 'zh-CN');
    const handleSetLanguage = (value: string) => {
        console.log(value);
        i18n.changeLanguage(value)
        setLanguage(value)
        props.onSetLanguage?.(value)
    }

    return (
        <Select value={language} onValueChange={handleSetLanguage} >
        <SelectTrigger className={triggerClass}>
        <GlobeIcon className='w-4 h-4' />
          <SelectValue className='hidden' placeholder={t('langName')} />
        </SelectTrigger>
        <SelectContent>
        {Object.entries(languages).map(([code, label]) => (
              <SelectItem key={code} value={code}>{label}</SelectItem>
            ))}
        </SelectContent>
      </Select>
    )
}
