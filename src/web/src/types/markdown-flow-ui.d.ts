import 'markdown-flow-ui/slide';

export {};

declare module 'markdown-flow-ui/slide' {
  interface Element {
    ask_list?: unknown[];
  }

  interface SlideProps {
    onPlaybackPositionChange?: (position: {
      audioKey: string;
      element?: Element;
      timeMs: number;
    }) => void;
    playbackResumeRequest?: {
      audioKey: string;
      id: number | string;
      timeMs: number;
    } | null;
  }
}
