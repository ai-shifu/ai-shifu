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
import i18n from '@/i18n';
import { browserLanguage } from '@/i18n';

import { type ClassValue } from "clsx"
import { cn } from '@/lib/utils'

type languageProps = {
    variant?: 'login' | 'standard'
    language?: string
    contentClassName?: ClassValue
    onSetLanguage?: (value: string) => void
  }

export default function LanguageSelect(props: languageProps) {
    const { t, i18n: i18nInstance } = useTranslation();
  const triggerClass =
      props.variant === 'login'
      ? 'w-[80px] h-[35px] rounded-lg p-0 flex items-center justify-center border-none shadow-none focus:outline-none'
          : 'flex items-center justify-start space-x-2 px-3 py-2 rounded-lg border-none hover:bg-gray-100 focus:ring-0 focus:ring-offset-0';

    
    const  language=props?.language || i18nInstance.language || browserLanguage;


    const handleSetLanguage = (value: string) => {
        i18n.changeLanguage(value)
        props.onSetLanguage?.(value)
    }

    return (
      <Select value={language} onValueChange={handleSetLanguage}>
        <SelectTrigger className={triggerClass}>
        <GlobeIcon className='w-4 h-4 mr-1' />
          <SelectValue className='hidden' placeholder={t('langName')} />
        </SelectTrigger>
        <SelectContent className={cn(props.contentClassName)}>
          {Object.entries(languages).map(([code, label]) => (
            <SelectItem key={code} value={code}>{label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    )
}
