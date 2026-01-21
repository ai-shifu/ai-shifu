'use client';

import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import styles from './VariableList.module.scss';
import type { PreviewVariablesMap } from './variableStorage';
import { Input } from '../ui/Input';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils';

interface VariableListProps {
  variables?: PreviewVariablesMap;
  hiddenVariables?: [string, string][];
  collapsed?: boolean;
  onToggle?: () => void;
  onChange?: (name: string, value: string) => void;
  variableOrder?: string[];
  onHideUnused?: () => void;
  onRestoreHidden?: () => void;
  disableHideUnused?: boolean;
}

const VariableList: React.FC<VariableListProps> = ({
  variables,
  hiddenVariables = [],
  collapsed = false,
  onToggle,
  onChange,
  variableOrder = [],
  onHideUnused,
  onRestoreHidden,
  disableHideUnused = false,
}) => {
  const { t } = useTranslation();
  const [showHidden, setShowHidden] = React.useState(false);
  const entries = useMemo(() => {
    const sourceEntries = Object.entries(variables || {});
    if (!variableOrder.length) {
      return sourceEntries;
    }
    const sourceMap = new Map(sourceEntries);
    const orderedEntries: [string, string][] = [];
    variableOrder.forEach(key => {
      if (sourceMap.has(key)) {
        orderedEntries.push([key, sourceMap.get(key) || '']);
        sourceMap.delete(key);
      }
    });
    sourceMap.forEach((value, key) => {
      orderedEntries.push([key, value]);
    });
    return orderedEntries;
  }, [variableOrder, variables]);

  const hasHidden = hiddenVariables.length > 0;
  const hasVisible = entries.length > 0;

  const isEmptyView = showHidden ? !hasHidden : !hasVisible;

  const renderActionsRight = () => (
    <div className={styles.actionsRight}>
      {!showHidden && onHideUnused && (
        <button
          type='button'
          className={styles.actionButton}
          onClick={onHideUnused}
          disabled={disableHideUnused}
        >
          {t('module.shifu.previewArea.variablesHideUnused')}
        </button>
      )}
      {showHidden && onRestoreHidden && (
        <button
          type='button'
          className={styles.actionButton}
          onClick={onRestoreHidden}
          disabled={!hasHidden}
        >
          {t('module.shifu.previewArea.variablesRestoreHidden')}
        </button>
      )}
    </div>
  );

  return (
    <div className={styles.variableList}>
      <div className={styles.header}>
        <div className={styles.topRow}>
          <div className={styles.titleWrapper}>
            <div className={styles.title}>
              {t('module.shifu.previewArea.variablesTitle')}
            </div>
            <div
              className={styles.description}
              title={t('module.shifu.previewArea.variablesDescription')}
            >
              {t('module.shifu.previewArea.variablesDescription')}
            </div>
          </div>
          {onToggle && (
            <button
              type='button'
              className={styles.toggle}
              onClick={onToggle}
            >
              {collapsed ? (
                <ChevronDown
                  size={16}
                  strokeWidth={2}
                />
              ) : (
                <ChevronUp
                  size={16}
                  strokeWidth={2}
                />
              )}
              <span>
                {collapsed
                  ? t('module.shifu.previewArea.variablesExpand')
                  : t('module.shifu.previewArea.variablesCollapse')}
              </span>
            </button>
          )}
        </div>
        {!collapsed && (
          <div className={styles.actionsRow}>
            <div className={styles.segmented}>
              <button
                type='button'
                className={cn(
                  styles.segmentedBtn,
                  !showHidden && styles.active,
                )}
                onClick={() => setShowHidden(false)}
              >
                {t('module.shifu.previewArea.variablesCurrent')}
              </button>
              <button
                type='button'
                className={cn(styles.segmentedBtn, showHidden && styles.active)}
                onClick={() => setShowHidden(true)}
              >
                {t('module.shifu.previewArea.variablesHiddenToggle')}
              </button>
            </div>
            {renderActionsRight()}
          </div>
        )}
      </div>
      {!isEmptyView && !showHidden && (
        <div
          className={`${styles.grid} ${collapsed ? styles.collapsed : ''}`}
          aria-hidden={collapsed}
        >
          {entries.map(([name, value]) => {
            const displayValue = value || '';
            return (
              <div
                className={styles.item}
                key={name}
              >
                <div
                  className={styles.name}
                  title={name}
                >
                  {name}
                </div>
                <div
                  className={styles.value}
                  title={displayValue}
                >
                  <Input
                    type='text'
                    value={displayValue}
                    placeholder={t(
                      'module.shifu.previewArea.variablesPlaceholder',
                    )}
                    onChange={e => {
                      const nextValue = e.target.value;
                      onChange?.(name, nextValue);
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {!isEmptyView && showHidden && (
        <div
          className={`${styles.hiddenSection} ${collapsed ? styles.collapsed : ''}`}
        >
          <div className={styles.hiddenList}>
            {hiddenVariables.map(([name, value], index) => {
              const displayValue = value || '';
              return (
                <div
                  key={`hidden-${name}-${index}`}
                  className={styles.item}
                >
                  <div
                    className={styles.name}
                    title={name}
                  >
                    {name}
                  </div>
                  <div className={styles.value}>
                    <Input
                      type='text'
                      value={displayValue}
                      placeholder={t(
                        'module.shifu.previewArea.variablesPlaceholder',
                      )}
                      onChange={e => {
                        const nextValue = e.target.value;
                        onChange?.(name, nextValue);
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {isEmptyView && (
        <div className={styles.hiddenEmpty}>
          {showHidden
            ? t('module.shifu.previewArea.variablesHiddenEmpty')
            : t('module.shifu.previewArea.variablesEmpty')}
        </div>
      )}
    </div>
  );
};

export default VariableList;
