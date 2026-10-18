# Two stages: build with every dev tool, then copy only the finished site into
# a small image. Next.js "standalone" output (next.config.js) traces which files
# the server needs, so the final image doesn't carry all of node_modules.

FROM node:20-alpine AS build

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies (the download cache is kept by Docker, not in the image)
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund

# Copy application code
COPY . .

# NEXT_PUBLIC_ values are baked in at build time.
# API address: empty means http://localhost:8000 (local use); the public site uses /api.
ARG NEXT_PUBLIC_API_BASE=
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
# Optional "Save to Spotify" button
ARG NEXT_PUBLIC_SPOTIFY_CLIENT_ID=
ENV NEXT_PUBLIC_SPOTIFY_CLIENT_ID=$NEXT_PUBLIC_SPOTIFY_CLIENT_ID
# Shown on the Privacy and Terms pages
ARG NEXT_PUBLIC_CONTACT_EMAIL=
ENV NEXT_PUBLIC_CONTACT_EMAIL=$NEXT_PUBLIC_CONTACT_EMAIL
ENV NEXT_TELEMETRY_DISABLED=1

# Build the application
RUN npm run build


FROM node:20-alpine

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
# Listen on every address inside the container (Docker sets HOSTNAME to the container id)
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

# The server and the few node_modules it uses, then the browser files and images
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

# Expose port
EXPOSE 3000

# Start the application
USER node
CMD ["node", "server.js"]
