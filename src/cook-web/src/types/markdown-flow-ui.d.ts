declare module 'markdown-flow-ui/renderer' {
  import { ComponentType, ReactNode } from 'react';

  export interface OnSendContentParams {
    variableName?: string;
    buttonText?: string;
    inputText?: string;
    [key: string]: any;
  }

  export interface CustomRenderBarProps {
    [key: string]: any;
  }

  export interface InteractionDefaultValueOptions {
    [key: string]: any;
  }

  export interface ContentRenderProps {
    content?: string;
    enableTypewriter?: boolean;
    typingSpeed?: number;
    readonly?: boolean;
    userInput?: string;
    customRenderBar?: (() => ReactNode | null) | ComponentType<any>;
    confirmButtonText?: string;
    copyButtonText?: string;
    copiedButtonText?: string;
    sandboxMode?: string;
    onSend?: (content: OnSendContentParams) => void;
    onClickCustomButtonAfterContent?: () => void;
    interactionDefaultValueOptions?: InteractionDefaultValueOptions;
    [key: string]: any;
  }

  export interface MarkdownFlowInputProps {
    placeholder?: string;
    value?: string;
    onChange?: (e: any) => void;
    onSend?: () => void;
    className?: string;
    [key: string]: any;
  }

  export interface RenderSegment {
    type: string;
    content: string;
    [key: string]: any;
  }

  export interface MarkdownFlowProps {
    interactionDefaultValueOptions?: InteractionDefaultValueOptions;
    [key: string]: any;
  }

  export interface IframeSandboxProps {
    [key: string]: any;
  }

  export interface SandboxAppProps {
    [key: string]: any;
  }

  export const ContentRender: ComponentType<ContentRenderProps>;
  export const MarkdownFlowInput: ComponentType<MarkdownFlowInputProps>;
  export const MarkdownFlow: ComponentType<MarkdownFlowProps>;
  export const IframeSandbox: ComponentType<IframeSandboxProps>;
  export function splitContentSegments(
    content: string,
    includeEmpty?: boolean,
  ): RenderSegment[];

  export default ContentRender;
  export type { OnSendContentParams, CustomRenderBarProps, RenderSegment };
}
