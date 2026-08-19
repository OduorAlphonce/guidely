import { useState, useMemo } from 'react'
import SourceCard from '../components/SourceCard.jsx'
import LoadingSpinner from '../components/LoadingSpinner.jsx'
import { searchDocuments } from '../api/search.js'

function highlightSources(answer, sources) {
  if (!sources.length) return answer
  const filenames = sources.map((s) => s.file)
  const pattern = new RegExp(
    `\\b(${filenames.map((f) => f.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})\\b`,
    'g',
  )
  const parts = answer.split(pattern)
  return parts.map((part, i) =>
    filenames.includes(part) ? (
      <mark key={i} className="answer-source-ref">{part}</mark>
    ) : (
      part
    ),
  )
}

export default function SearchPage() {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState(null)
  const [isSearching, setIsSearching] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed) return

    setIsSearching(true)
    setError(null)
    setResult(null)
    try {
      const data = await searchDocuments(trimmed)
      setResult({
        answer: data.answer,
        sources: data.sources,
        latencyMs: data.latency_ms,
      })
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.')
    } finally {
      setIsSearching(false)
    }
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSubmit(event)
    }
  }

  const answerNodes = useMemo(() => {
    if (!result) return null
    return highlightSources(result.answer, result.sources)
  }, [result])

  const showEmpty = !isSearching && !result && !error

  return (
    <section className="page">
      {showEmpty && (
        <div className="search-hero">
          <h1>Mwongozo</h1>
          <p className="search-hero-sub">
            Ask questions about your uploaded documents — policies, guides, FAQs, manuals.
            Every answer cites the source so you can verify it.
          </p>
        </div>
      )}

      <form className="search-bar" onSubmit={handleSubmit}>
        <input
          type="text"
          className="search-input"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about your documents..."
          disabled={isSearching}
        />
        <button
          type="submit"
          className="search-send"
          disabled={!question.trim() || isSearching}
          aria-label="Send"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </form>

      {showEmpty && (
        <div className="search-hints">
          <p>How it works:</p>
          <ul>
            <li>Upload documents via the <strong>Admin</strong> page (or use the sample docs that ship with the project).</li>
            <li>Type a natural-language question above and press <strong>Enter</strong>.</li>
            <li>Mwongozo searches your documents for relevant passages and generates a cited answer.</li>
          </ul>
          <p className="search-hint-examples">Try: "How many remote work days are allowed?" or "How do I file an expense report?"</p>
        </div>
      )}

      {isSearching && <LoadingSpinner label="Searching your documents…" />}

      {error && (
        <div className="search-error" role="alert">
          <h2>Sorry, that did not work</h2>
          <p>{error}</p>
          <button type="button" className="search-error-dismiss" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {!isSearching && result && (
        <div className="search-result">
          <h2>Answer</h2>
          <p className="answer">{answerNodes}</p>
          {result.latencyMs != null && (
            <p className="answer-meta">Answered in {(result.latencyMs / 1000).toFixed(2)}s</p>
          )}

          <h2>Sources ({result.sources.length})</h2>
          <div className="sources-list">
            {result.sources.map((source, index) => (
              <SourceCard key={`${source.file}-${index}`} source={source} rank={index + 1} />
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
