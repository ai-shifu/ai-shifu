'use client';

import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import styles from './MemoryList.module.scss';
import type { PreviewMemoryMap } from './memoryStorage';
import { Input } from '../ui/Input';
import { ChevronDown, ChevronUp, X } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface MemoryListProps {
  memory?: PreviewMemoryMap;
  collapsed?: boolean;
  onToggle?: () => void;
  onChange?: (name: string, value: string) => void;
  memoryOrder?: string[];
  systemMemoryKeys?: string[];
  actionType?: 'hide' | 'restore';
  onAction?: () => void;
  actionDisabled?: boolean;
  customMemoryKeys?: string[];
  unusedMemoryKeys?: string[];
  onHideMemory?: (name: string) => void;
}

const SYSTEM_MEMORY_LABEL_KEYS = {
  sys_user_nickname: 'module.shifu.previewArea.systemMemoryLabels.nickname',
  sys_user_style: 'server.profile.style',
  sys_user_background: 'module.shifu.previewArea.systemMemoryLabels.background',
  sys_user_input: 'module.shifu.previewArea.systemMemoryLabels.input',
  sys_user_language: 'module.shifu.previewArea.systemMemoryLabels.language',
} as const;

const resolveSystemMemoryLabelKey = (name: string) =>
  SYSTEM_MEMORY_LABEL_KEYS[name as keyof typeof SYSTEM_MEMORY_LABEL_KEYS];

const MemoryList: React.FC<MemoryListProps> = ({
  memory,
  collapsed = false,
  onToggle,
  onChange,
  memoryOrder = [],
  systemMemoryKeys,
  actionType,
  onAction,
  actionDisabled = false,
  customMemoryKeys,
  unusedMemoryKeys,
  onHideMemory,
}) => {
  const { t } = useTranslation();

  const isHideAction = actionType === 'hide';
  const customKeySet = useMemo(
    () => new Set(customMemoryKeys || []),
    [customMemoryKeys],
  );
  const unusedKeySet = useMemo(
    () => new Set(unusedMemoryKeys || []),
    [unusedMemoryKeys],
  );
  const systemMemoryKeySet = useMemo(
    () => new Set(systemMemoryKeys || []),
    [systemMemoryKeys],
  );

  const entries = useMemo(() => {
    const sourceEntries = Object.entries(memory || {});
    if (!memoryOrder.length) {
      return sourceEntries;
    }
    const sourceMap = new Map(sourceEntries);
    const orderedEntries: [string, string][] = [];
    memoryOrder.forEach(key => {
      if (sourceMap.has(key)) {
        orderedEntries.push([key, sourceMap.get(key) || '']);
        sourceMap.delete(key);
      }
    });
    sourceMap.forEach((value, key) => {
      orderedEntries.push([key, value]);
    });
    return orderedEntries;
  }, [memoryOrder, memory]);

  const hasVisible = entries.length > 0;
  const isEmptyView = !hasVisible;

  return (
    <TooltipProvider delayDuration={200}>
      <div className={styles.memoryList}>
        <div className={styles.header}>
          <div className={styles.topRow}>
            <div className={styles.titleWrapper}>
              <div className={styles.title}>
                {t('module.shifu.previewArea.memoryTitle')}
              </div>
              <div
                className={styles.description}
                title={t('module.shifu.previewArea.memoryDescription')}
              >
                {t('module.shifu.previewArea.memoryDescription')}
              </div>
            </div>
            <div className={styles.actionsCompact}>
              {actionType && onAction && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type='button'
                      className={styles.actionButton}
                      onClick={onAction}
                      disabled={actionDisabled}
                    >
                      {isHideAction
                        ? t('module.shifu.previewArea.memoryHideUnused')
                        : t('module.shifu.previewArea.memoryRestoreHidden')}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side='top'>
                    {isHideAction
                      ? t('module.shifu.previewArea.memoryHideUnusedTooltip')
                      : t(
                          'module.shifu.previewArea.memoryRestoreHiddenTooltip',
                        )}
                  </TooltipContent>
                </Tooltip>
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
                      ? t('module.shifu.previewArea.memoryExpand')
                      : t('module.shifu.previewArea.memoryCollapse')}
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
              const systemMemoryLabelKey = systemMemoryKeySet.has(name)
                ? resolveSystemMemoryLabelKey(name)
                : undefined;
              const displayName = systemMemoryLabelKey
                ? t(systemMemoryLabelKey)
                : name;
              return (
                <div
                  className={styles.item}
                  key={name}
                >
                  {systemMemoryLabelKey ? (
                    <div
                      tabIndex={0}
                      className={`${styles.name} ${styles.systemName}`}
                      aria-label={t(
                        'module.shifu.previewArea.systemMemoryLabels.accessibleName',
                        { label: displayName, name },
                      )}
                    >
                      <span
                        className={styles.friendlyName}
                        aria-hidden='true'
                      >
                        {displayName}
                      </span>
                      <span
                        className={styles.rawName}
                        dir='ltr'
                        aria-hidden='true'
                      >
                        {name}
                      </span>
                    </div>
                  ) : (
                    <div
                      className={styles.name}
                      title={name}
                    >
                      {displayName}
                    </div>
                  )}
                  <div
                    className={styles.value}
                    title={displayValue}
                  >
                    <Input
                      type='text'
                      value={displayValue}
                      placeholder={t(
                        'module.shifu.previewArea.memoryPlaceholder',
                      )}
                      onChange={e => {
                        const nextValue = e.target.value;
                        onChange?.(name, nextValue);
                      }}
                    />
                    {canHide && onHideMemory && (
                      <button
                        type='button'
                        className={styles.hideBadge}
                        onClick={event => {
                          event.stopPropagation();
                          onHideMemory(name);
                        }}
                        aria-label={t(
                          'module.shifu.previewArea.memoryHideSingleConfirmTitle',
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
                </div>
              );
            })}
          </div>
        )}

        {isEmptyView && (
          <div className={styles.hiddenEmpty}>
            {t('module.shifu.previewArea.memoryEmpty')}
          </div>
        )}
      </div>
    </TooltipProvider>
  );
};

export default MemoryList;
