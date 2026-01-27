import { memo, useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import Reveal from 'reveal.js';
import 'reveal.js/dist/reveal.css';
import 'reveal.js/dist/theme/white.css';
import ContentIframe from './ContentIframe';
import type { ChatContentItem } from './useChatLogicHook';
import './ListenModeRenderer.scss';

interface ListenModeRendererProps {
  items: ChatContentItem[];
  mobileStyle: boolean;
  chatRef: React.RefObject<HTMLDivElement>;
  containerClassName?: string;
  isLoading?: boolean;
  sectionTitle?: string;
}

const ListenModeRenderer = ({
  items,
  mobileStyle,
  chatRef,
  containerClassName,
  isLoading = false,
  sectionTitle,
}: ListenModeRendererProps) => {
  const deckRef = useRef<Reveal.Api | null>(null);

  useEffect(() => {
    if (!chatRef.current || deckRef.current) {
      return;
    }

    deckRef.current = new Reveal(chatRef.current, {
      transition: 'slide',
      margin: 0,
      minScale: 1,
      maxScale: 1,
      progress: false,
      controls: true, // debug
    });

    deckRef.current.initialize().then(() => {
      console.log('Reveal initialized');
    });

    return () => {
      try {
        console.log('销毁reveal实例');
        deckRef.current?.destroy();
        deckRef.current = null;
      } catch (e) {
        console.warn('Reveal.js destroy 調用失敗。');
      }
    };
  }, [chatRef]);

  useEffect(() => {
    if (!deckRef.current || isLoading) {
      return;
    }
    if (typeof deckRef.current.sync !== 'function') {
      return;
    }
    // Ensure Reveal picks up newly rendered slides
    try {
      console.log('sync reveal实例');
      deckRef.current.sync();
      deckRef.current.layout();
      const targetIndex = Math.max(items.length - 1, 0);
      deckRef.current.slide(targetIndex);
    } catch (error) {
      console.warn('Reveal sync failed', error);
    }
  }, [items, isLoading]);

  return (
    <div
      className={cn(containerClassName, 'listen-reveal-wrapper')}
      style={{ background: '#F7F9FF' }}
    >
      <div
        className={cn('reveal', 'listen-reveal')}
        ref={chatRef}
      >
        <div className='slides'>
          {!isLoading &&
            items.map((item, idx) => {
              const baseKey = item.generated_block_bid || `${item.type}-${idx}`;
              console.log('item=====', item.content);
              return (
                <ContentIframe
                  key={baseKey}
                  item={item}
                  mobileStyle={mobileStyle}
                  blockBid={item.generated_block_bid}
                  sectionTitle={sectionTitle}
                />
              );
            })}
        </div>
      </div>
    </div>
  );
};

ListenModeRenderer.displayName = 'ListenModeRenderer';

export default memo(ListenModeRenderer);
