import { useState } from 'react'
import SourceCard from '../components/SourceCard.jsx'
import { searchDocuments } from '../api/search.js'

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
    try {
      const data = await searchDocuments(trimmed)
      setResult({
        answer: data.answer,
        sources: data.sources,
        latencyMs: data.latency_ms,
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setIsSearching(false)
    }
  }

  return (
    <section>
      <h1>Search</h1>
      <p>Ask a question and get answers cited from your documents.</p>
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

      {error && (
        <p className="search-error" role="alert">
          {error}
        </p>
      )}

      {result && (
        <div className="search-result">
          <h2>Answer</h2>
          <p className="answer">{result.answer}</p>
          {result.latencyMs != null && (
            <p className="answer-meta">Answered in {(result.latencyMs / 1000).toFixed(2)}s</p>
          )}

          <h2>Sources</h2>
          <div className="sources-list">
            {result.sources.map((source, index) => (
              <SourceCard key={`${source.file}-${index}`} source={source} />
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
