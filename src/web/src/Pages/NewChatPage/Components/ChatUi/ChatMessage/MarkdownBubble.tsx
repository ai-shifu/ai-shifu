import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import MermaidRenderer from 'Components/MermaidRenderer';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Bubble } from '@ai-shifu/chatui';
import { Image } from 'antd';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import classNames from 'classnames';
import styles from './MarkdownBubble.module.scss';
import CopyButton from './CopyButton';

interface MarkdownBubbleProps {
  content: string;
  mobileStyle?: boolean;
  isStreaming?: boolean;
  onImageLoaded?: () => void;
}

interface CodeComponentProps {
  node?: any;
  inline?: boolean;
  className?: string;
  children: React.ReactNode;
  [key: string]: any;
}

export const MarkdownBubble = (props: MarkdownBubbleProps) => {
  const { mobileStyle, onImageLoaded } = props;

  const copyToClipboard = (content: string) => {
    navigator.clipboard.writeText(content);
  };

  const getLanguageFromClassName = (className?: string): string | null => {
    const match = /language-(\w+)/.exec(className || '');
    return match ? match[1] : null;
  };

  const renderInlineCode = (className?: string, children?: React.ReactNode, props?: any) => (
    <code
      {...props}
      className={classNames(className, styles.inlineCode)}
    >
      {children}
    </code>
  );

  const renderMermaidDiagram = (children: React.ReactNode) => (
    <MermaidRenderer code={String(children)} isStreaming={props.isStreaming} />
  );

  const renderCodeBlock = (language: string, children: React.ReactNode, props: any) => (
    <div
      className="markdown-code_block"
      style={{ position: 'relative' }}
    >
      <CopyButton content={String(children)} />
      <SyntaxHighlighter
        {...props}
        children={String(children).replace(/\n$/, '')}
        style={vscDarkPlus}
        language={language}
        showLineNumbers={!mobileStyle}
        wrapLines={false}
        onCopy={() => copyToClipboard(String(children))}
      />
    </div>
  );

  const renderCodeComponent = ({ node, inline, className, children, ...props }: CodeComponentProps) => {
    const language = getLanguageFromClassName(className);

    // Inline code
    if (inline) {
      return renderInlineCode(className, children, props);
    }

    // Mermaid diagram
    if (language === 'mermaid') {
      return renderMermaidDiagram(children);
    }

    // Code block
    return renderCodeBlock(language || 'text', children, props);
  };

  return (
    <>
      <Bubble>
        <ReactMarkdown
          children={props.content}
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw]}
          components={{
            code: renderCodeComponent,
            img(imgProps) {
              return (
                <Image
                  {...imgProps}
                  width={imgProps.style?.width || '100%'}
                  preview={!props.isStreaming}
                  style={{ borderRadius: '5px' }}
                  onLoad={onImageLoaded}
                ></Image>
              );
            },
          }}
        />
      </Bubble>
    </>
  );
};

export default memo(MarkdownBubble);
