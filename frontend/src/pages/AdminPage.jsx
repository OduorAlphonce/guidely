import { useState, useEffect, useRef } from 'react'
import { listDocuments, uploadDocument, deleteDocument, reindexAll } from '../api/documents.js'

function formatSize(bytes) {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`
}

function formatDate(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function AdminPage() {
  const [documents, setDocuments] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [reindexing, setReindexing] = useState(false)
  const [deleting, setDeleting] = useState(null)
  const [tagFilter, setTagFilter] = useState('')
  const [allTags, setAllTags] = useState([])
  const [reindexResult, setReindexResult] = useState(null)
  const fileInputRef = useRef(null)

  async function fetchDocuments() {
    setIsLoading(true)
    setError(null)
    try {
      const data = await listDocuments(tagFilter || undefined)
      setDocuments(data)
      const tags = new Set()
      data.forEach((doc) => doc.tags?.forEach((t) => tags.add(t)))
      setAllTags([...tags].sort())
    } catch (err) {
      setError(err.message || 'Failed to load documents')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchDocuments()
  }, [tagFilter])

  async function handleUpload(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      await uploadDocument(file)
      await fetchDocuments()
    } catch (err) {
      setError(err.message || 'Upload failed')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function handleDelete(doc) {
    if (!window.confirm(`Delete "${doc.filename}"? This cannot be undone.`)) return
    setDeleting(doc.id)
    setError(null)
    try {
      await deleteDocument(doc.id)
      await fetchDocuments()
    } catch (err) {
      setError(err.message || 'Delete failed')
    } finally {
      setDeleting(null)
    }
  }

  async function handleReindex() {
    setReindexing(true)
    setError(null)
    setReindexResult(null)
    try {
      const result = await reindexAll()
      setReindexResult(result)
      await fetchDocuments()
    } catch (err) {
      setError(err.message || 'Reindex failed')
    } finally {
      setReindexing(false)
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <h1>Admin</h1>
        <p>Upload, manage, and reindex your documents.</p>
      </header>

      <div className="admin-toolbar">
        <div className="admin-toolbar-left">
          <label className="admin-upload-btn btn" disabled={uploading}>
            {uploading ? 'Uploading...' : 'Upload Document'}
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.md"
              onChange={handleUpload}
              hidden
              disabled={uploading}
            />
          </label>
          <button
            className="btn btn-secondary"
            onClick={handleReindex}
            disabled={reindexing}
          >
            {reindexing ? 'Reindexing...' : 'Reindex All'}
          </button>
        </div>
        {allTags.length > 0 && (
          <div className="admin-tag-filter">
            <label htmlFor="tag-filter">Filter by tag:</label>
            <select
              id="tag-filter"
              value={tagFilter}
              onChange={(e) => setTagFilter(e.target.value)}
            >
              <option value="">All tags</option>
              {allTags.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {error && (
        <div className="search-error" role="alert">
          <h2>Error</h2>
          <p>{error}</p>
          <button type="button" className="search-error-dismiss" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {reindexResult && (
        <div className="admin-reindex-result">
          <h3>Reindex Complete</h3>
          <p>
            Total: {reindexResult.total} |
            Indexed: {reindexResult.indexed} |
            Skipped: {reindexResult.skipped} |
            Failed: {reindexResult.failed}
          </p>
          {reindexResult.results?.filter((r) => r.status === 'failed').length > 0 && (
            <ul className="admin-reindex-errors">
              {reindexResult.results
                .filter((r) => r.status === 'failed')
                .map((r, i) => (
                  <li key={i}>{r.file}: {r.error}</li>
                ))}
            </ul>
          )}
          <button
            type="button"
            className="search-error-dismiss"
            onClick={() => setReindexResult(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {isLoading ? (
        <div className="loading-spinner">
          <div className="loading-spinner-icon" />
          <span>Loading documents...</span>
        </div>
      ) : documents.length === 0 ? (
        <div className="admin-empty">
          <p>No documents indexed yet.</p>
          <p>Upload a .txt or .md file to get started.</p>
        </div>
      ) : (
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Size</th>
                <th>Status</th>
                <th>Tags</th>
                <th>Updated</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id}>
                  <td className="admin-table-filename">{doc.filename}</td>
                  <td>{formatSize(doc.size_bytes)}</td>
                  <td>
                    <span className={`admin-status admin-status-${doc.status}`}>
                      {doc.status}
                    </span>
                  </td>
                  <td>
                    {doc.tags?.length > 0 ? (
                      <div className="admin-tags">
                        {doc.tags.map((t) => (
                          <span key={t} className="admin-tag">{t}</span>
                        ))}
                      </div>
                    ) : (
                      <span className="admin-tags-empty">-</span>
                    )}
                  </td>
                  <td>{formatDate(doc.updated_at)}</td>
                  <td>
                    <button
                      className="btn btn-danger-sm"
                      onClick={() => handleDelete(doc)}
                      disabled={deleting === doc.id}
                    >
                      {deleting === doc.id ? 'Deleting...' : 'Delete'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
