import { memo, useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import Reveal from 'reveal.js';
import 'reveal.js/dist/reveal.css';
import 'reveal.js/dist/theme/white.css';
import ContentIframe from './ContentIframe';
import type { ChatContentItem } from './useChatLogicHook';

interface ListenModeRendererProps {
  items: ChatContentItem[];
  mobileStyle: boolean;
  chatRef: React.RefObject<HTMLDivElement>;
  containerClassName?: string;
  isLoading?: boolean;
}

const ListenModeRenderer = ({
  items,
  mobileStyle,
  chatRef,
  containerClassName,
  isLoading = false,
}: ListenModeRendererProps) => {
  const deckRef = useRef<Reveal.Api | null>(null);

  useEffect(() => {
    if (!chatRef.current || deckRef.current) {
      return;
    }

    deckRef.current = new Reveal(chatRef.current, {
      transition: 'slide',
    });

    deckRef.current.initialize().then(() => {
      console.log('Reveal initialized');
    });

    return () => {
      try {
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
    // Ensure Reveal picks up newly rendered slides
    deckRef.current.sync();
    deckRef.current.layout();
    deckRef.current.slide(0);
  }, [items, isLoading]);

  return (
    <div
      className={cn(containerClassName, 'reveal flex')}
      ref={chatRef}
      style={{ width: '100%', height: '100%', overflowY: 'auto' }}
    >
      <div className='slides flex flex-1 flex-col'>
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
              />
            );
          })}
      </div>
    </div>
  );
};

ListenModeRenderer.displayName = 'ListenModeRenderer';

export default memo(ListenModeRenderer);
