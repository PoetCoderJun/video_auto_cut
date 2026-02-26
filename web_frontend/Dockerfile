# Railway (and other PaaS): Next.js frontend. Set NEXT_PUBLIC_SITE_URL / NEXT_PUBLIC_API_BASE at build time.
# Use Debian-based image: @libsql/client native bindings require glibc (Alpine/musl causes fcntl64 symbol not found).
FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
# Build-time env (Railway injects these; set in Service Variables and redeploy)
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_API_BASE
ARG BETTER_AUTH_SECRET
ENV NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
# Better Auth validates secret during next build; use placeholder so build passes. Runtime uses Railway Variables.
ENV BETTER_AUTH_SECRET=${BETTER_AUTH_SECRET:-build-time-placeholder-min-32-chars-for-next-build}
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
