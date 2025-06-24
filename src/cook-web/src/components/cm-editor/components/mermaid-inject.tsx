'use client'

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import mermaid from 'mermaid'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogOverlay } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

type MermaidResource = {
  mermaidCode: string
}

type MermaidInjectProps = {
  value?: MermaidResource
  onSelect: (resource: MermaidResource) => void
}

type ViewMode = 'both' | 'code' | 'diagram'

const MermaidInject: React.FC<MermaidInjectProps> = ({ value, onSelect }) => {
  const { t } = useTranslation()
  const [code, setCode] = useState(value?.mermaidCode || 'graph TD\n    A[Start] --> B[End]')
  const [debouncedCode, setDebouncedCode] = useState(code)
  const [viewMode, setViewMode] = useState<ViewMode>('both')
  const [renderError, setRenderError] = useState<string | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [renderedSvg, setRenderedSvg] = useState<string>('')
  const svgContainerRef = useRef<HTMLDivElement>(null)
  const modalSvgRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'default',
      securityLevel: 'loose'
    })
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedCode(code)
    }, 300)

    return () => clearTimeout(timer)
  }, [code])

  const renderMermaid = useCallback(async (mermaidCode: string, containerId: string) => {
    if (!mermaidCode.trim()) return

    try {
      setRenderError(null)
      const { svg } = await mermaid.render(containerId, mermaidCode)
      setRenderedSvg(svg)
      return svg
    } catch (error) {
      console.error('Mermaid render error:', error)
      setRenderError(error instanceof Error ? error.message : 'Failed to render diagram')
      return null
    }
  }, [])

  useEffect(() => {
    if (debouncedCode && svgContainerRef.current) {
      renderMermaid(debouncedCode, `mermaid-preview-${Date.now()}`)
        .then(svg => {
          if (svg && svgContainerRef.current) {
            svgContainerRef.current.innerHTML = svg
          }
        })
    }
  }, [debouncedCode, renderMermaid])

  useEffect(() => {
    if (isModalOpen && renderedSvg && modalSvgRef.current) {
      modalSvgRef.current.innerHTML = renderedSvg
    }
  }, [isModalOpen, renderedSvg])

  const handleSelect = () => {
    onSelect({ mermaidCode: code })
  }

  const handleSvgClick = () => {
    setIsModalOpen(true)
  }

  const handleModalClose = () => {
    setIsModalOpen(false)
  }

  const handleCopySource = async () => {
    try {
      await navigator.clipboard.writeText(code)
    } catch (error) {
      console.error('Failed to copy to clipboard:', error)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      handleModalClose()
    }
  }

  return (
    <div className="space-y-4">
      {/* View Mode Selector */}
      <div className="flex justify-end">
        <Select value={viewMode} onValueChange={(value: ViewMode) => setViewMode(value)}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="both">{t('cm-editor.code-and-diagram')}</SelectItem>
            <SelectItem value="code">{t('cm-editor.code-only')}</SelectItem>
            <SelectItem value="diagram">{t('cm-editor.diagram-only')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Main Content */}
      <div className="flex gap-4 min-h-[400px]">
        {/* Code Editor */}
        {(viewMode === 'both' || viewMode === 'code') && (
          <div className="flex-1">
            <textarea
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="w-full h-full min-h-[400px] p-3 border rounded-md font-mono text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Enter Mermaid diagram code..."
            />
          </div>
        )}

        {/* Preview */}
        {(viewMode === 'both' || viewMode === 'diagram') && (
          <div className="flex-1">
            {renderError ? (
              <div className="w-full h-full min-h-[400px] p-3 border rounded-md bg-red-50 border-red-200">
                <div className="text-red-600 text-sm">
                  <strong>Render Error:</strong>
                  <pre className="mt-2 whitespace-pre-wrap">{renderError}</pre>
                </div>
              </div>
            ) : (
              <div
                ref={svgContainerRef}
                className="w-full h-full min-h-[400px] p-3 border rounded-md overflow-auto cursor-pointer hover:bg-gray-50"
                onClick={handleSvgClick}
              />
            )}
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex justify-end">
        <Button className="h-8" onClick={handleSelect} disabled={!code.trim()}>
          {t('common.confirm')}
        </Button>
      </div>

      {/* Full Screen Modal */}
      <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
        <DialogOverlay
          className="fixed inset-0 bg-black/50 z-[100]"
          onClick={handleModalClose}
        />
        <DialogContent
          className="fixed inset-0 z-[101] flex items-center justify-center p-4"
          onKeyDown={handleKeyDown}
        >
          <div className="bg-white rounded-lg shadow-xl max-w-[90vw] max-h-[90vh] overflow-hidden">
            {/* Modal Header */}
            <div className="flex justify-between items-center p-4 border-b">
              <h3 className="text-lg font-semibold">{t('cm-editor.mermaid')}</h3>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCopySource}
                >
                  {t('cm-editor.copy-source')}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleModalClose}
                >
                  ×
                </Button>
              </div>
            </div>

            {/* Modal Content */}
            <div className="p-4 overflow-auto" style={{ minWidth: '80vw', maxHeight: '70vh' }}>
              <div
                ref={modalSvgRef}
                className="flex justify-center items-center"
              />
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default MermaidInject
