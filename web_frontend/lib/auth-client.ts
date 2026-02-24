import {createAuthClient} from "better-auth/react";
import {jwtClient} from "better-auth/client/plugins";

const baseURL = process.env.NEXT_PUBLIC_SITE_URL || "http://127.0.0.1:3000";

export const authClient = createAuthClient({
  baseURL,
  plugins: [jwtClient()],
});
