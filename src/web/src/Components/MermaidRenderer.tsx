import React, { useEffect, useRef, useId } from 'react';
import mermaid from 'mermaid';

interface Props {
  code: string;
  isStreaming?: boolean;
}

export default function MermaidRenderer({ code, isStreaming = false }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const isMermaidInitialized = useRef(false);
  const uniqueId = useId();

  useEffect(() => {
    const renderMermaid = async () => {
      if (!container.current) return;

      if (!isMermaidInitialized.current) {
        mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });
        isMermaidInitialized.current = true;
      }

      try {
        // First, try to parse the code. This will throw an error on syntax issues.
        await mermaid.parse(code);

        // Only if parsing is successful, render the diagram.
        const { svg } = await mermaid.render('mermaid-svg-' + uniqueId.replace(/:/g, '-'), code);
        if (container.current) {
          container.current.innerHTML = svg;
        }
      } catch (error: unknown) {
        if (container.current) {
          if (isStreaming) {
            // In streaming mode, do nothing on error to keep the last valid diagram.
            return;
          } else {
            // In non-streaming mode, display the error message.
            const pre = document.createElement('pre');
            pre.className = 'text-red-500 whitespace-pre-wrap';
            const message = error instanceof Error ? error.message : String(error);
            pre.textContent = `Mermaid Syntax Error: ${message}`;
            container.current.innerHTML = '';
            container.current.appendChild(pre);
          }
        }
      }
    };

    // Do not render empty code to avoid mermaid parsing errors on initial empty state.
    if (code.trim()) {
      renderMermaid();
    }

  }, [code, isStreaming]);

  return (
    <div
      ref={container}
      className="w-full max-h-[60vh] overflow-auto rounded-md"
    />
  );
}
