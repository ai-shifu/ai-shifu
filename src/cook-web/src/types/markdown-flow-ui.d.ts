import 'markdown-flow-ui/renderer';
import 'markdown-flow-ui/slide';
import type { InteractionDefaultValueOptions } from 'markdown-flow-ui/renderer';

export {};

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
  interface Element {
    ask_list?: unknown[];
  }
}
