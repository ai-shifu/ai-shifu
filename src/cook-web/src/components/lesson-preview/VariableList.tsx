'use client';

import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import styles from './VariableList.module.scss';
import type { PreviewVariablesMap } from './variableStorage';
import { Input } from '../ui/Input';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface VariableListProps {
  variables?: PreviewVariablesMap;
  collapsed?: boolean;
  onToggle?: () => void;
  onChange?: (name: string, value: string) => void;
}

const VariableList: React.FC<VariableListProps> = ({
  variables,
  collapsed = false,
  onToggle,
  onChange,
}) => {
  const { t } = useTranslation();
  const entries = useMemo(() => {
    return Object.entries(variables || {});
  }, [variables]);

  if (!entries.length) {
    return null;
  }

  return (
    <div className={styles.variableList}>
      <div className={styles.header}>
        <div className={styles.titleWrapper}>
          <div className={styles.title}>
            {t('module.shifu.previewArea.variablesTitle')}
          </div>
          <div className={styles.description}>
            {t('module.shifu.previewArea.variablesDescription')}
            {/* <span className={styles.link}>
              {t('module.shifu.previewArea.variablesLearnMore')}
            </span> */}
          </div>
        </div>
        {onToggle && (
          <button
            type='button'
            className={styles.toggle}
            onClick={onToggle}
          >
            {collapsed ? (
              <ChevronDown size={16} strokeWidth={2} />
            ) : (
              <ChevronUp size={16} strokeWidth={2} />
            )}
            <span>
              {collapsed
                ? t('module.shifu.previewArea.variablesExpand')
                : t('module.shifu.previewArea.variablesCollapse')}
            </span>
          </button>
        )}
      </div>
      <div
        className={`${styles.grid} ${collapsed ? styles.collapsed : ''}`}
        aria-hidden={collapsed}
      >
        {entries.map(([name, value]) => {
          const displayValue = value || '';
          return (
            <div className={styles.item} key={name}>
              <div className={styles.name} title={name}>{name}</div>
              <div className={styles.value} title={displayValue}>
                <Input
                  type='text'
                  value={displayValue}
                  placeholder={t('module.shifu.previewArea.variablesPlaceholder')}
                  onChange={e => {
                    const nextValue = e.target.value;
                    console.log('e', nextValue);
                    onChange?.(name, nextValue);
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default VariableList;
