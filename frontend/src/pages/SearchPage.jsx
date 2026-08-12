import { useState } from 'react'
import SourceCard from '../components/SourceCard.jsx'

const SAMPLE_RESULT = {
  answer:
    'Full-time employees in good standing are eligible for remote work up to 4 days per week with manager approval. Core hours are 10 AM - 3 PM ET, Monday through Friday, and employees must be available via Slack or phone during core hours.',
  sources: [
    {
      file: 'policy.txt',
      score: 0.92,
      snippet:
        'All full-time employees in good standing are eligible for remote work up to 4 days per week. Manager approval is required for any arrangement exceeding this limit. Part-time employees may request a prorated schedule.',
      text: '1. Eligibility\nAll full-time employees in good standing are eligible for remote work up to 4 days per week. Manager approval is required for any arrangement exceeding this limit. Part-time employees may request a prorated schedule. Contractors and interns require explicit VP-level approval.',
    },
    {
      file: 'policy.txt',
      score: 0.88,
      snippet:
        'Core hours are 10 AM - 3 PM ET, Monday through Friday. Employees must be available via Slack or phone during core hours. Outside of core hours, teams have flexibility to set their own schedules.',
      text: '3. Work Hours and Availability\nCore hours are 10 AM - 3 PM ET, Monday through Friday. Employees must be available via Slack or phone during core hours. Outside of core hours, teams have flexibility to set their own schedules as long as business needs are met. Overtime must be pre-approved by your manager.',
    },
    {
      file: 'faq.txt',
      score: 0.81,
      snippet:
        'Q: How do I enroll in health insurance? A: New hires must enroll within 30 days of their start date. Open enrollment runs annually from November 1-30.',
      text: 'HR FAQs\nQ: How do I enroll in health insurance?\nA: New hires must enroll within 30 days of their start date. Open enrollment runs annually from November 1-30. Visit the benefits portal at benefits.company.com to make changes. Coverage typically begins on the first of the month following enrollment.',
    },
  ],
}

export default function SearchPage() {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState(null)

  function handleSubmit(event) {
    event.preventDefault()
    if (!question.trim()) return
    setResult(SAMPLE_RESULT)
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
        <button type="submit" className="search-submit" disabled={!question.trim()}>
          Ask
        </button>
      </form>

      {result && (
        <div className="search-result">
          <h2>Answer</h2>
          <p className="answer">{result.answer}</p>

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
