'use client';

import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import styles from './VariableList.module.scss';
import type { PreviewVariablesMap } from './variableStorage';

interface VariableListProps {
  variables?: PreviewVariablesMap;
}

const VariableList: React.FC<VariableListProps> = ({ variables }) => {
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
            <span className={styles.link}>
              {t('module.shifu.previewArea.variablesLearnMore')}
            </span>
          </div>
        </div>
      </div>
      <div className={styles.grid}>
        {entries.map(([name, value]) => {
          const displayValue = value || '';
          return (
            <div className={styles.item} key={name} title={`${name}: ${displayValue}`}>
              <div className={styles.name}>{name}</div>
              <div className={styles.value}>{displayValue}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default VariableList;
