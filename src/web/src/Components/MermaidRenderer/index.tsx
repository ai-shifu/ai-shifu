import React, { useEffect, useRef } from 'react';
import mermaid from 'mermaid';

interface Props {
  code: string;
}

export default function MermaidRenderer({ code }: Props) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (container.current) {
      mermaid.initialize({ startOnLoad: false });
      mermaid.render('mermaid-svg-' + Date.now(), code).then((result) => {
        if (container.current) {
          container.current.innerHTML = result.svg;
        }
      }).catch((error) => {
        if (container.current) {
          container.current.innerHTML = `<pre style="color: red;">Mermaid Error: ${error.message}</pre>`;
        }
      });
    }
  }, [code]);

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
