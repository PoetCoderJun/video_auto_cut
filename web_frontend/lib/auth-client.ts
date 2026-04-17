import {createAuthClient} from "better-auth/react";
import {jwtClient} from "better-auth/client/plugins";

export function resolveAuthClientBaseURL(): string {
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin.replace(/\/$/, "");
  }
  return (process.env.NEXT_PUBLIC_SITE_URL || "http://127.0.0.1:3000").replace(/\/$/, "");
}

export const authClient = createAuthClient({
  baseURL: resolveAuthClientBaseURL(),
  plugins: [jwtClient()],
});
