// frontend/utils/fetcher.js
// Utility for making API calls to the backend

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export { API_BASE };

/**
 * A random id for this browser, sent with every request, so song edits count as one
 * listener's (and your own edits show on your maps) without needing an account.
 */
export function listenerId() {
  if (typeof window === "undefined") return null;
  try {
    let id = window.localStorage.getItem("sm-listener-id");
    if (!id) {
      id = (window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`).replace(/[^A-Za-z0-9_-]/g, "");
      window.localStorage.setItem("sm-listener-id", id);
    }
    return id;
  } catch {
    return null; // private window or blocked storage: edits need a listener id, everything else works
  }
}

/**
 * Fetch from the backend API
 */
function accountToken() {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem("sm-token");
  } catch {
    return null;
  }
}

export async function apiFetch(path, options = {}) {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  
  const ours = url.startsWith(API_BASE); // only our own server gets who you are
  const lid = ours ? listenerId() : null;
  const token = ours ? accountToken() : null;
  const defaultOptions = {
    headers: {
      "Content-Type": "application/json",
      ...(lid ? { "X-Listener-Id": lid } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
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

