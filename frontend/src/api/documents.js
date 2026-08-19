import API_BASE from './config.js'

const BASE = `${API_BASE}/api/documents`

export async function listDocuments(tag) {
  const url = tag ? `${BASE}/?tag=${encodeURIComponent(tag)}` : `${BASE}/`
  const res = await fetch(url)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || `Failed to list documents (${res.status})`)
  }
  return res.json()
}

export async function uploadDocument(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/upload`, { method: 'POST', body: form })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || `Upload failed (${res.status})`)
  }
  return res.json()
}

export async function deleteDocument(docId) {
  const res = await fetch(`${BASE}/${encodeURIComponent(docId)}`, { method: 'DELETE' })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || `Delete failed (${res.status})`)
  }
  return res.json()
}

export async function reindexAll() {
  const res = await fetch(`${BASE}/reindex`, { method: 'POST' })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || `Reindex failed (${res.status})`)
  }
  return res.json()
}
