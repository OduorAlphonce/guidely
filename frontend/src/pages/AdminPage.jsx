import { useCallback, useEffect, useRef, useState } from 'react'
import {
  listDocuments,
  uploadDocument,
  deleteDocument,
  reindexAll,
} from '../api/documents'

function formatBytes(n) {
  if (n === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(n) / Math.log(1024))
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`
}

function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const STATUS_LABELS = {
  ready: 'Indexed',
  pending: 'Pending',
  indexing: 'Indexing…',
  error: 'Error',
}

export default function AdminPage() {
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [reindexing, setReindexing] = useState(false)
  const [reindexResult, setReindexResult] = useState(null)
  const [editingDoc, setEditingDoc] = useState(null)
  const [editContent, setEditContent] = useState('')
  const [editSaving, setEditSaving] = useState(false)
  const fileInput = useRef(null)

  const loadDocs = useCallback(async () => {
    try {
      setError(null)
      const data = await listDocuments()
      setDocs(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadDocs()
  }, [loadDocs])

  async function handleUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      await uploadDocument(file)
      await loadDocs()
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  async function handleDelete(doc) {
    if (!window.confirm(`Delete "${doc.filename}"? This cannot be undone.`)) return
    setError(null)
    try {
      await deleteDocument(doc.id)
      setDocs((prev) => prev.filter((d) => d.id !== doc.id))
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleReindex() {
    setReindexing(true)
    setReindexResult(null)
    setError(null)
    try {
      const result = await reindexAll()
      setReindexResult(result)
      await loadDocs()
    } catch (err) {
      setError(err.message)
    } finally {
      setReindexing(false)
    }
  }

  function startEdit(doc) {
    setEditingDoc(doc)
    setEditContent('')
    fetch(`/api/documents/${doc.id}/content`)
      .then((r) => {
        if (!r.ok) throw new Error('Cannot load file content')
        return r.json()
      })
      .then((data) => setEditContent(data.content))
      .catch(() => setEditContent('— Preview not available for this file type —'))
  }

  function cancelEdit() {
    setEditingDoc(null)
    setEditContent('')
  }

  async function saveEdit() {
    if (!editingDoc) return
    setEditSaving(true)
    try {
      const blob = new Blob([editContent], { type: 'text/plain' })
      const file = new File([blob], editingDoc.filename, { type: 'text/plain' })
      await deleteDocument(editingDoc.id)
      await uploadDocument(file)
      setEditingDoc(null)
      setEditContent('')
      await loadDocs()
    } catch (err) {
      setError(err.message)
    } finally {
      setEditSaving(false)
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <h1>Admin</h1>
        <p>Upload, manage, and re-index your documents.</p>
      </header>

      <div className="admin-toolbar">
        <input
          ref={fileInput}
          type="file"
          accept=".txt,.md,.pdf"
          onChange={handleUpload}
          style={{ display: 'none' }}
        />
        <button
          className="btn btn-primary"
          onClick={() => fileInput.current?.click()}
          disabled={uploading || reindexing}
        >
          {uploading ? 'Uploading…' : 'Upload Document'}
        </button>
        <button
          className="btn btn-secondary"
          onClick={handleReindex}
          disabled={reindexing || uploading}
        >
          {reindexing ? (
            <span className="btn-spinner">
              <span className="loading-spinner-icon" /> Re-indexing…
            </span>
          ) : (
            'Re-index All'
          )}
        </button>
      </div>

      {error && (
        <div className="search-error">
          <p>{error}</p>
          <button className="search-error-dismiss" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {reindexResult && (
        <div className="reindex-result">
          <strong>Re-index complete:</strong>{' '}
          {reindexResult.indexed} indexed, {reindexResult.skipped} skipped,{' '}
          {reindexResult.failed} failed out of {reindexResult.total} files.
        </div>
      )}

      {loading ? (
        <div className="loading-spinner">
          <span className="loading-spinner-icon" /> Loading documents…
        </div>
      ) : docs.length === 0 ? (
        <div className="search-empty">
          <span className="search-empty-title">No documents yet</span>
          <p className="search-empty-text">
            Upload a .txt, .md, or .pdf file to get started.
          </p>
        </div>
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Filename</th>
                <th className="admin-th-num">Size</th>
                <th>Last Indexed</th>
                <th>Status</th>
                <th className="admin-th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr key={doc.id}>
                  <td className="admin-filename">{doc.filename}</td>
                  <td className="admin-td-num">{formatBytes(doc.size_bytes)}</td>
                  <td>{formatDate(doc.updated_at)}</td>
                  <td>
                    <span className={`status-badge status-${doc.status}`}>
                      {STATUS_LABELS[doc.status] || doc.status}
                    </span>
                  </td>
                  <td className="admin-actions">
                    <button
                      className="btn-icon"
                      title="Preview / Edit"
                      onClick={() => startEdit(doc)}
                    >
                      &#9998;
                    </button>
                    <button
                      className="btn-icon btn-icon-danger"
                      title="Delete"
                      onClick={() => handleDelete(doc)}
                    >
                      &#128465;
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editingDoc && (
        <div className="modal-overlay" onClick={cancelEdit}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{editingDoc.filename}</h2>
              <button className="modal-close" onClick={cancelEdit}>
                &times;
              </button>
            </div>
            <textarea
              className="modal-editor"
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              spellCheck={false}
            />
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={cancelEdit} disabled={editSaving}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={saveEdit} disabled={editSaving}>
                {editSaving ? 'Saving…' : 'Save & Re-index'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
