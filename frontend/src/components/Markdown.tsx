import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * Render an assistant answer as markdown.
 *
 * react-markdown builds elements from the markdown syntax itself and drops raw
 * HTML in the source, so no sanitising step and no `dangerouslySetInnerHTML`
 * are needed. GFM adds tables and strikethrough on top of CommonMark.
 */
export default function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
          // A table wider than the bubble scrolls on its own instead of
          // stretching the whole chat column.
          table: ({ node: _node, ...props }) => (
            <div className="markdown-table-wrap">
              <table {...props} />
            </div>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}
