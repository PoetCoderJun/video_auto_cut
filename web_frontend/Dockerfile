# Railway (and other PaaS): Next.js frontend. Set NEXT_PUBLIC_SITE_URL / NEXT_PUBLIC_API_BASE at build time.
# Use Debian-based image: @libsql/client native bindings require glibc (Alpine/musl causes fcntl64 symbol not found).
FROM node:20-slim AS builder

WORKDIR /app

# better-sqlite3 (Better Auth dep) needs node-gyp → Python + build-essential
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
# Build-time env (Railway injects these; set in Service Variables and redeploy)
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_API_BASE
ARG BETTER_AUTH_SECRET
ARG TURSO_DATABASE_URL
ARG TURSO_AUTH_TOKEN
ENV NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
# Better Auth validates these during next build; placeholders so build passes. Runtime uses Railway Variables.
ENV BETTER_AUTH_SECRET=${BETTER_AUTH_SECRET:-build-time-placeholder-min-32-chars-for-next-build}
ENV TURSO_DATABASE_URL=${TURSO_DATABASE_URL:-libsql://build-placeholder.turso.io}
ENV TURSO_AUTH_TOKEN=${TURSO_AUTH_TOKEN:-build-placeholder-token}
RUN npm run build

FROM node:20-slim AS runner

WORKDIR /app
ENV NODE_ENV=production
RUN groupadd --gid 1001 nodejs && useradd --uid 1001 --gid nodejs --create-home nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
# Railway sets PORT at runtime
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
CMD ["node", "server.js"]
