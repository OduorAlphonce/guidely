import { useState } from 'react'

export default function SourceCard({ source }) {
  const [expanded, setExpanded] = useState(false)
  const { file, snippet, score, text } = source
  const detail = text ?? snippet

  return (
    <article className="source-card">
      <header className="source-card-header">
        <span className="source-card-file" title={file}>
          {file}
        </span>
        {typeof score === 'number' && (
          <span className="source-card-score">{Math.round(score * 100)}%</span>
        )}
        <button
          type="button"
          className="source-card-toggle"
          onClick={() => setExpanded((prev) => !prev)}
          aria-expanded={expanded}
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      </header>
      <p className="source-card-snippet">{expanded ? detail : snippet}</p>
    </article>
  )
}
