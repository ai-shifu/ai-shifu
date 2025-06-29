import React, { useEffect, useRef } from 'react';
import mermaid from 'mermaid';

interface Props {
  code: string;
  isStreaming?: boolean;
}

export default function MermaidRenderer({ code, isStreaming = false }: Props) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const renderMermaid = async () => {
      if (!container.current) return;

      mermaid.initialize({ startOnLoad: false });

      try {
        // First, try to parse the code. This will throw an error on syntax issues.
        await mermaid.parse(code);

        // Only if parsing is successful, render the diagram.
        const { svg } = await mermaid.render('mermaid-svg-' + Date.now(), code);
        if (container.current) {
          container.current.innerHTML = svg;
        }
      } catch (error: any) {
        if (container.current) {
          if (isStreaming) {
            // In streaming mode, do nothing on error to keep the last valid diagram.
            return;
          } else {
            // In non-streaming mode, display the error message.
            container.current.innerHTML = `<pre style="color: red;">Mermaid Syntax Error: ${error.message}</pre>`;
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
      style={{
        width: '100%',
        maxHeight: '60vh',
        overflow: 'auto',
        borderRadius: '6px',
      }}
    />
  );
}
