import 'markdown-flow-ui/slide';

export {};

declare module 'markdown-flow-ui/slide' {
  interface Element {
    ask_list?: unknown[];
  }
}
