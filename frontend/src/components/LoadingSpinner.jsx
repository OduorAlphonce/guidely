export default function LoadingSpinner({ label = 'Loading…' }) {
  return (
    <div className="loading-spinner" role="status">
      <span className="loading-spinner-icon" aria-hidden="true" />
      <span className="loading-spinner-text">{label}</span>
    </div>
  )
}
