import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
import { browserLanguage, normalizeLanguage } from '@/i18n';
import { localeCodes, localeEntries } from '@/lib/i18n-locales';
import { useTracking } from '@/hooks/useTracking';

import { type ClassValue } from 'clsx';
import { cn } from '@/lib/utils';

type languageProps = {
  variant?: 'login' | 'standard';
  analyticsSurface: 'login' | 'learner_menu' | 'admin_menu';
  language?: string;
  contentClassName?: ClassValue;
  onSetLanguage?: (value: string) => void;
};

export const LANGUAGE_SELECTION_EVENT = 'user_language_selected';

export default function LanguageSelect(props: languageProps) {
  const { t, i18n: i18nInstance } = useTranslation();
  const { trackEvent } = useTracking();
  const pendingSelectionRef = useRef<string | null>(null);
  const triggerClass =
    props.variant === 'login'
      ? 'w-[80px] h-[35px] rounded-lg p-0 flex items-center justify-center border-none shadow-none focus:outline-none'
      : 'w-full flex items-center justify-between px-3 py-2 rounded-lg border-none hover:bg-gray-100 focus:ring-0 focus:ring-offset-0';

  const language = normalizeLanguage(
    props?.language || i18nInstance.language || browserLanguage,
  );

  useEffect(() => {
    pendingSelectionRef.current = null;
  }, [language]);

  const handleSetLanguage = (value: string) => {
    if (!localeCodes.includes(value)) {
      return;
    }
    const normalizedValue = normalizeLanguage(value);
    if (
      normalizedValue === language ||
      pendingSelectionRef.current === normalizedValue
    ) {
      return;
    }
    pendingSelectionRef.current = normalizedValue;
    try {
      void Promise.resolve(
        trackEvent(LANGUAGE_SELECTION_EVENT, {
          selected_locale: normalizedValue,
          surface: props.analyticsSurface,
        }),
      ).catch(() => {});
    } catch {
      // Analytics must not block a language change.
    }
    try {
      void Promise.resolve(i18n.changeLanguage(normalizedValue)).catch(() => {
        if (pendingSelectionRef.current === normalizedValue) {
          pendingSelectionRef.current = null;
        }
      });
    } catch (error) {
      pendingSelectionRef.current = null;
      throw error;
    }
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
