import API_BASE from './config.js'

export async function searchDocuments(question) {
  const response = await fetch(`${API_BASE}/api/search/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ question }),
  })

  if (!response.ok) {
    let message = `Search failed (${response.status}). Please try again.`
    try {
      const data = await response.json()
      if (data.detail) {
        message = data.detail
      }
    } catch {
      // response body was not JSON; keep the generic message
    }
    throw new Error(message)
  }

  return response.json()
}
