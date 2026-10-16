FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

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

# Expose port
EXPOSE 3000

# Start the application
ENV NODE_ENV=production
CMD ["npm", "start"]

