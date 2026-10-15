// Old links (/map, /map?share=..., /map?csv=...) now open the home page
import { useEffect } from "react";
import { useRouter } from "next/router";

export default function OldMapLink() {
  const router = useRouter();
  useEffect(() => {
    if (!router.isReady) return;
    const q = new URLSearchParams(router.query).toString();
    router.replace(q ? `/?${q}` : "/");
  }, [router]);
  return null;
}
