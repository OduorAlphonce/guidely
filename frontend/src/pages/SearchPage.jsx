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

  const answerNodes = useMemo(() => {
    if (!result) return null
    return highlightSources(result.answer, result.sources)
  }, [result])

  return (
    <section className="page">
      <header className="page-header">
        <h1>Search</h1>
        <p>Ask a question and get answers cited from your documents.</p>
      </header>

      <form className="search-form" onSubmit={handleSubmit}>
        <label className="search-form-label" htmlFor="question">
          Your question
        </label>
        <textarea
          id="question"
          rows="4"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="e.g. How many remote days do I get?"
        />
        <button
          type="submit"
          className="search-submit"
          disabled={!question.trim() || isSearching}
        >
          {isSearching ? 'Searching…' : 'Ask'}
        </button>
      </form>

      {isSearching && <LoadingSpinner label="Searching your documents…" />}

      {!isSearching && !result && !error && (
        <div className="search-empty">
          <span className="search-empty-title">Ready when you are</span>
          <p className="search-empty-text">
            Ask a question above and you will get an answer with the documents it was
            based on.
          </p>
        </div>
      )}

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
