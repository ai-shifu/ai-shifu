import 'markdown-flow-ui/renderer';
import 'markdown-flow-ui/slide';
import type { InteractionDefaultValueOptions } from 'markdown-flow-ui/renderer';
import type {
  SlidePlayerCustomActions,
  SlidePlayerTexts,
} from 'markdown-flow-ui/slide';
import type { ReactNode } from 'react';

export {};

type MarkdownFlowMobileViewMode = 'nonFullscreen' | 'fullscreen';

declare module 'markdown-flow-ui/renderer' {
  interface ContentRenderProps {
    userInput?: string;
    interactionDefaultValueOptions?: InteractionDefaultValueOptions;
  }

  interface MarkdownFlowProps {
    interactionDefaultValueOptions?: InteractionDefaultValueOptions;
  }
}

declare module 'markdown-flow-ui/slide' {
  interface SlidePlayerTexts {
    nonFullscreenLabel?: string;
    fullscreenLabel?: string;
  }

  interface Element {
    ask_list?: unknown[];
  }

  interface SlideProps {
    interactionDefaultValueOptions?: InteractionDefaultValueOptions;
    playerCustomActions?: SlidePlayerCustomActions;
    playerCustomActionPauseOnActive?: boolean;
    fullscreenHeader?: {
      content?: ReactNode;
      backAriaLabel?: string;
      onBack?: () => void;
    };
    playerTexts?: SlidePlayerTexts;
    onMobileViewModeChange?: (viewMode: MarkdownFlowMobileViewMode) => void;
  }
}
