declare module 'markdown-flow-ui/renderer' {
  interface ContentRenderProps {
    userInput?: string;
    interactionDefaultValueOptions?: InteractionDefaultValueOptions;
  }

  interface MarkdownFlowProps {
    interactionDefaultValueOptions?: InteractionDefaultValueOptions;
  }

  interface SlideProps {
    interactionDefaultValueOptions?: InteractionDefaultValueOptions;
  }
}
