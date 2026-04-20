import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
import { browserLanguage, normalizeLanguage } from '@/i18n';
import { localeEntries } from '@/lib/i18n-locales';

import { type ClassValue } from 'clsx';
import { cn } from '@/lib/utils';

type languageProps = {
  variant?: 'login' | 'standard';
  language?: string;
  contentClassName?: ClassValue;
  onSetLanguage?: (value: string) => void;
};

export default function LanguageSelect(props: languageProps) {
  const { t, i18n: i18nInstance } = useTranslation();
  const triggerClass =
    props.variant === 'login'
      ? 'w-[80px] h-[35px] rounded-lg p-0 flex items-center justify-center border-none shadow-none focus:outline-none'
      : 'w-full flex items-center justify-between px-3 py-2 rounded-lg border-none hover:bg-gray-100 focus:ring-0 focus:ring-offset-0';

  const language = normalizeLanguage(
    props?.language || i18nInstance.language || browserLanguage,
  );

  const handleSetLanguage = (value: string) => {
    const normalizedValue = normalizeLanguage(value);
    i18n.changeLanguage(normalizedValue);
    props.onSetLanguage?.(normalizedValue);
  };

  return (
    <Select
      value={language}
      onValueChange={handleSetLanguage}
    >
      <SelectTrigger className={triggerClass}>
        <SelectValue placeholder={t('common.language.name')} />
      </SelectTrigger>
      <SelectContent className={cn(props.contentClassName)}>
        {localeEntries.map(([code, info]) => (
          <SelectItem
            key={code}
            value={code}
          >
            {info.label ?? code}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
