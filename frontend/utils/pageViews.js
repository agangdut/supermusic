// Counts a page view for the site's own visitor stats (Admin > Visitors).
// Sends only the page's route (/u/[username], never the real name or anything after "?")
// and the site the visitor came from. No cookies; the server keeps no IP address.
import { API_BASE } from "@/utils/fetcher";

let last = null;

export function countPageView(route) {
  // The admin page itself isn't counted, so checking the numbers doesn't change them
  if (typeof window === "undefined" || route === last || route === "/_error" || route === "/admin") return;
  if (navigator.doNotTrack === "1" || navigator.globalPrivacyControl) return;
  last = route;
  const first = !countPageView.sent;
  countPageView.sent = true;
  // Only the first page of a visit has a meaningful referrer
  const referrer = first && document.referrer ? document.referrer : null;
  try {
    fetch(`${API_BASE}/stats/view`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: route, referrer }),
      keepalive: true,
    }).catch(() => {});
  } catch {
    // stats never get in the way
  }
}
