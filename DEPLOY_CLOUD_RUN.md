# Deploying ZainAI to Google Cloud Run

This setup containerizes the **ZainAI 3D Video Conference Stage** ([`web/index.html`](web/index.html)) with FastAPI and WebSockets, allowing it to run globally on Google Cloud Run.

---

## 1. Local Testing with Docker

### Using Docker Compose
```bash
# 1. Export your Gemini API Key
export GEMINI_API_KEY="your_actual_gemini_api_key"

# 2. Build and start the container
docker compose up --build
```
Then open your browser to **http://localhost:8080**.

### Or using plain Docker commands
```bash
docker build -t zainai-conference .
docker run -p 8080:8080 -e GEMINI_API_KEY="your_actual_gemini_api_key" zainai-conference
```

---

## 2. Deploying to Google Cloud Run

Google Cloud Run can build directly from source using Google Cloud Build:

### One-Command Deployment
```bash
gcloud run deploy zainai-conference \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080 \
  --memory 2Gi \
  --cpu 2 \
  --set-env-vars GEMINI_API_KEY="your_actual_gemini_api_key"
```

### Important Settings for Cloud Run:
- **WebSocket Support**: Cloud Run automatically enables WebSocket connections on HTTP/2.
- **Session Affinity**: If scaling to multiple instances, enable session affinity:
  ```bash
  gcloud run services update zainai-conference --session-affinity --region us-central1
  ```
- **Custom Domain**: You can map your own domain (e.g. `ai.yourdomain.com`) in the Google Cloud Console under *Cloud Run > Manage Custom Domains*.

---

## 3. Architecture Overview in Cloud Run
- **Frontend**: Served from `/app/web` directly over HTTPS/WSS.
- **3D Assets**: `/avatar/lipsync_eyes.glb` served statically from `/app/avatar`.
- **Compute**: Runs headless FastAPI + WebSockets via [`headless_server.py`](headless_server.py).
- **Client Processing**: Three.js WebGL avatar rendering, camera capture, microphone capture, and Web Audio all execute on the user's client browser, keeping Cloud Run resource consumption very low.
