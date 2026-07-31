# Build context is frontend/ (this directory) - see docker-compose.yml.
#
# NEXT_PUBLIC_* variables are inlined into the client JS bundle at build
# time by Next.js, not read at container start - there is no way around
# this without a runtime string-replace step. Pass the target backend URL
# as a build arg (docker build --build-arg NEXT_PUBLIC_API_URL=... or the
# `args:` block in docker-compose.yml). If you need one image deployable
# against multiple backend URLs without rebuilding, that needs an
# entrypoint-time placeholder-replace script - not implemented here since
# this is an internal tool with a small, known set of environments.

FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# npm's own predev/prebuild lifecycle hook would try to run
# generate-builds-json.js against a data/ dir that doesn't exist in this
# build context - --ignore-scripts skips it here; the builder stage below
# runs `npm run build`, whose prebuild hook handles it with the real
# fallback-to-empty-builds.json behavior already built into that script.
RUN npm ci --ignore-scripts

FROM node:24-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

# Standalone output already traces and includes only the node_modules the
# app actually uses - copying node_modules wholesale (like the deps stage
# has) here would defeat the entire point of output: "standalone".
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "fetch('http://localhost:3000/').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["node", "server.js"]
