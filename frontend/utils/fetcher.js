// frontend/utils/fetcher.js
// Utility for making API calls to the backend

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export { API_BASE };

/**
 * Fetch from the backend API
 */
export async function apiFetch(path, options = {}) {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  
  const defaultOptions = {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  };

  // Remove Content-Type for FormData
  if (options.body instanceof FormData) {
    delete defaultOptions.headers["Content-Type"];
  }

  const response = await fetch(url, {
    ...defaultOptions,
    ...options,
    headers: {
      ...defaultOptions.headers,
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    const errorText = await response.text();
    let errorData;
    try {
      errorData = JSON.parse(errorText);
    } catch {
      errorData = { detail: errorText };
    }
    throw new Error(errorData.detail || errorData.message || `HTTP ${response.status}: ${response.statusText}`);
  }

  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/json")) {
    return response.json();
  }
  
  return response.text();
}

