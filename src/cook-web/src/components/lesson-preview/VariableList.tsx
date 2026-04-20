'use client';

import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import styles from './VariableList.module.scss';
import type { PreviewVariablesMap } from './variableStorage';
import { Input } from '../ui/Input';
import { ChevronDown, ChevronUp, X } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface VariableListProps {
  variables?: PreviewVariablesMap;
  collapsed?: boolean;
  onToggle?: () => void;
  onChange?: (name: string, value: string) => void;
  variableOrder?: string[];
  actionType?: 'hide' | 'restore';
  onAction?: () => void;
  actionDisabled?: boolean;
  customVariableKeys?: string[];
  unusedVariableKeys?: string[];
  onHideVariable?: (name: string) => void;
}

const VariableList: React.FC<VariableListProps> = ({
  variables,
  collapsed = false,
  onToggle,
  onChange,
  variableOrder = [],
  actionType,
  onAction,
  actionDisabled = false,
  customVariableKeys,
  unusedVariableKeys,
  onHideVariable,
}) => {
  const { t } = useTranslation();

  const isHideAction = actionType === 'hide';
  const customKeySet = useMemo(
    () => new Set(customVariableKeys || []),
    [customVariableKeys],
  );
  const unusedKeySet = useMemo(
    () => new Set(unusedVariableKeys || []),
    [unusedVariableKeys],
  );

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

  const hasVisible = entries.length > 0;
  const isEmptyView = !hasVisible;

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
          <div className={styles.actionsCompact}>
            {actionType && onAction && (
              <TooltipProvider delayDuration={200}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type='button'
                      className={styles.actionButton}
                      onClick={onAction}
                      disabled={actionDisabled}
                    >
                      {isHideAction
                        ? t('module.shifu.previewArea.variablesHideUnused')
                        : t('module.shifu.previewArea.variablesRestoreHidden')}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side='top'>
                    {isHideAction
                      ? t('module.shifu.previewArea.variablesHideUnusedTooltip')
                      : t(
                          'module.shifu.previewArea.variablesRestoreHiddenTooltip',
                        )}
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
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
        </div>
      </div>
      {!isEmptyView && (
        <div
          className={`${styles.grid} ${collapsed ? styles.collapsed : ''}`}
          aria-hidden={collapsed}
        >
          {entries.map(([name, value]) => {
            const displayValue = value || '';
            const canHide = customKeySet.has(name) && unusedKeySet.has(name);
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
                {canHide && onHideVariable && (
                  <button
                    type='button'
                    className={styles.hideBadge}
                    onClick={event => {
                      event.stopPropagation();
                      onHideVariable(name);
                    }}
                    aria-label={t(
                      'module.shifu.previewArea.variablesHideSingleConfirmTitle',
                    )}
                  >
                    <X
                      size={12}
                      strokeWidth={2}
                      aria-hidden='true'
                    />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {isEmptyView && (
        <div className={styles.hiddenEmpty}>
          {t('module.shifu.previewArea.variablesEmpty')}
        </div>
      )}
    </div>
  );
};

export default VariableList;
