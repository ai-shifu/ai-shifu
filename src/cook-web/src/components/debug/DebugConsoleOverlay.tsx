'use client';

import React from 'react';
import { Button } from '@/components/ui/Button';
import { ScrollArea } from '@/components/ui/ScrollArea';
import {
  type DebugConsoleEntry,
  type DebugConsoleLevel,
  formatConsoleArgs,
} from '@/c-utils/debugConsole';

const MAX_ENTRIES = 200;
const CONSOLE_METHODS: DebugConsoleLevel[] = ['log', 'info', 'warn', 'error'];

const DEBUG_LEVEL_STYLES: Record<DebugConsoleLevel, string> = {
  log: 'text-slate-100',
  info: 'text-sky-300',
  warn: 'text-amber-300',
  error: 'text-rose-300',
};

const buildEntry = (
  level: DebugConsoleLevel,
  args: unknown[],
): DebugConsoleEntry => ({
  id: `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
  level,
  message: formatConsoleArgs(args),
  timestamp: new Date().toISOString(),
});

type DebugConsoleOverlayProps = {
  enabled: boolean;
};

export const DebugConsoleOverlay = ({ enabled }: DebugConsoleOverlayProps) => {
  const [entries, setEntries] = React.useState<DebugConsoleEntry[]>([]);
  const [expanded, setExpanded] = React.useState(true);

  React.useLayoutEffect(() => {
    if (!enabled) {
      return;
    }

    const originalConsole = {
      log: console.log,
      info: console.info,
      warn: console.warn,
      error: console.error,
    };

    const appendEntry = (level: DebugConsoleLevel, args: unknown[]) => {
      const nextEntry = buildEntry(level, args);
      setEntries(previousEntries => {
        const nextEntries = [...previousEntries, nextEntry];
        if (nextEntries.length <= MAX_ENTRIES) {
          return nextEntries;
        }
        return nextEntries.slice(nextEntries.length - MAX_ENTRIES);
      });
    };

    CONSOLE_METHODS.forEach(level => {
      console[level] = (...args: unknown[]) => {
        appendEntry(level, args);
        originalConsole[level](...args);
      };
    });

    console.info('[debug-overlay] console capture enabled', {
      path:
        typeof window !== 'undefined'
          ? `${window.location.pathname}${window.location.search}`
          : '',
    });

    return () => {
      CONSOLE_METHODS.forEach(level => {
        console[level] = originalConsole[level];
      });
    };
  }, [enabled]);

  if (!enabled) {
    return null;
  }

  return (
    <div className='fixed inset-x-3 bottom-3 z-[1300] flex justify-end md:inset-x-auto md:right-4'>
      <div className='w-full max-w-[720px] rounded-xl border border-slate-700/80 bg-slate-950/95 text-slate-50 shadow-2xl backdrop-blur md:w-[720px]'>
        <div className='flex items-center justify-between gap-3 border-b border-slate-800 px-3 py-2'>
          <div className='min-w-0'>
            <div className='text-sm font-semibold text-slate-50'>
              Debug Console
            </div>
            <div className='truncate text-xs text-slate-400'>
              {entries.length} logs captured on this page
            </div>
          </div>
          <div className='flex items-center gap-2'>
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800'
              onClick={() => setEntries([])}
            >
              Clear
            </Button>
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800'
              onClick={() => setExpanded(previousExpanded => !previousExpanded)}
            >
              {expanded ? 'Collapse' : 'Expand'}
            </Button>
          </div>
        </div>

        {expanded ? (
          <ScrollArea className='h-[42dvh] w-full'>
            <div className='space-y-2 px-3 py-3 font-mono text-xs leading-5'>
              {entries.length ? (
                entries.map(entry => (
                  <div
                    key={entry.id}
                    className='rounded-lg border border-slate-800 bg-slate-900/80 px-3 py-2'
                  >
                    <div className='mb-1 flex items-center gap-2 text-[11px] uppercase tracking-[0.08em] text-slate-500'>
                      <span>{entry.level}</span>
                      <span>{entry.timestamp}</span>
                    </div>
                    <ScrollArea className='w-full whitespace-nowrap'>
                      <pre
                        className={`inline-block min-w-full whitespace-pre ${DEBUG_LEVEL_STYLES[entry.level]}`}
                      >
                        {entry.message}
                      </pre>
                    </ScrollArea>
                  </div>
                ))
              ) : (
                <div className='rounded-lg border border-dashed border-slate-800 px-3 py-4 text-slate-500'>
                  Waiting for console output...
                </div>
              )}
            </div>
          </ScrollArea>
        ) : null}
      </div>
    </div>
  );
};

export default DebugConsoleOverlay;
