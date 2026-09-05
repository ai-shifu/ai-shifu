import 'markdown-flow-ui/slide';

declare module 'markdown-flow-ui/slide' {
  interface Element {
    ask_list?: unknown[];
  }

  interface SlideProps {
    onPlaybackCheckpoint?: (checkpoint: {
      audioKey: string;
      element: Element;
      isComplete: boolean;
      stepIndex: number;
      timeMs: number;
    }) => void;
    playbackRestoreRequest?: {
      audioKey: string;
      id: number | string;
      timeMs: number;
    } | null;
  }
}
