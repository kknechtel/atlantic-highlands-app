# Build context is the repo root (see docker-compose.yml): the build reads
# the town's profile from municipalities/<MUNICIPALITY>/profile.json.
FROM node:20-alpine AS builder

ARG MUNICIPALITY=atlantic-highlands-nj
WORKDIR /app
COPY web/package.json web/package-lock.json* ./
RUN npm ci
COPY web/ .
COPY municipalities/ /municipalities/
ENV MUNICIPALITY=${MUNICIPALITY} MUNICIPALITY_DIR=/municipalities/${MUNICIPALITY}
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
