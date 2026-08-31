# Rforum – Real-time Audience Engagement Platform

**Transform Your Presentations Into Interactive Experiences**

Rforum is a modern, feature-rich audience engagement platform that enables live, real-time interaction between moderators and audience members. Create polls, Q&A sessions, feedback forms, and content slides while monitoring live responses and engagement metrics in real-time with instant synchronization across all connected devices.

## Platform Images

#### Admin Dashboard - User Management
![Admin Dashboard - User Management](./images/admin-view1.png)
*Super admins can manage all users, assign roles (Moderator/Super Admin), track user activity, and manage account status*

#### Admin Dashboard - Platform Analytics & Storage
![Admin Dashboard - Analytics](./images/admin-view2.png)
*Monitor platform-wide statistics including storage usage, total files, user distribution, and usage metrics*

#### Moderator Dashboard - Session Management
![Moderator Dashboard](./images/mod-dashboard1.png)
*View sessions with status indicators, session codes, moderator names, speakers, and quick actions to manage, edit, or delete sessions*

#### Moderator - Event Management
![Moderator Events](./images/mod-event1.png)
*Organize sessions under events, manage event details, publication status, and link multiple sessions to themed events*

#### Moderator - Session Control & Analytics
![Moderator Analytics](./images/mod-analytics1.png)
*Real-time analytics showing event metrics, session statistics, content distribution (polls, Q&A, feedback, word clouds), engagement by format, response trends, and feedback ratings*

#### Moderator - Live Session Control
![Moderator Session](./images/mod-session-1.png)
*Session control panel with session code, moderator details, speakers list, and session management options to go live, edit, or delete*

#### Moderator - Session Management View
![Moderator Session Manage](./images/mod-viewsessionmanage.png)
*Comprehensive session management interface with detailed view options, session controls, and management capabilities*

#### Moderator - Main Screen
![Moderator Main Screen](./images/modview-mainscreen.png)
*Main screen dashboard showing upcoming sessions, events, assets, and live session controls for moderators*

#### Guest Audience View
![Guest View](./images/guest-view.png)
*Simple interface for audience members to join with a session code and participate in polls, Q&A, feedback, and word cloud activities*

## Core Features

### Interactive Content Types

- **Live Polls**: Real-time bar charts with instant updates
- **Q&A Board**: Crowdsource questions with community upvoting
- **Feedback Forms**: Collect feedback with optional ratings (1-5 stars)
- **Word Clouds**: Visualize keywords as dynamic clouds
- **Content Slides**: Display static content alongside interactive elements

### Session Management

- **Easy Guest Access**: Join with 8-character code, no registration required
- **Moderator Control**: Manage slides and monitor responses in real-time
- **Speaker Identification**: Track moderator and speaker names
- **Session State**: Toggle between live and draft modes

### Real-time Communication

- **Instant Sync**: WebSocket updates, no page refreshes
- **Live Updates**: Responses appear instantly across devices
- **Live Metrics**: Monitor participants and engagement in real-time

### Analytics & Insights

- **Metrics**: Track sessions, events, participants, responses, and trends
- **Response Export**: Download detailed data with timestamps
- **Role-based Views**: Admins see platform-wide stats; users see their own

### Administration & Security

- **User Management**: Manage users, assign roles, track activity, activate/deactivate accounts
- **Content Moderation**: Delete or moderate sessions and events
- **JWT Authentication**: Secure token-based auth with configurable expiration
- **Role-Based Access**: Different permissions for users and super admins

### File Management

- **Session Assets**: Upload materials linked to sessions/events
- **Formats**: PDF, PowerPoint, Word, text, OpenDocument
- **Limits**: Configurable max (default 20 MB per file)
- **PDF Processing**: Automatic analysis for compatibility

### Event Organization

- **Create Events**: Group sessions with dates and descriptions
- **Publish**: Control visibility and publication status
- **Link Sessions**: Associate multiple sessions per event

### Mobile & Cross-Platform

- **Responsive Design**: Works seamlessly on desktop, tablet, and mobile
- **Touch Optimized**: Optimized controls and interactions for touch devices
- **No Installation**: Access via any modern web browser – no apps needed

## Technology Stack

**Backend**: FastAPI, Python 3.10+, PostgreSQL 13+, SQLAlchemy 2.0, WebSockets/Redis, JWT auth  
**Frontend**: SvelteKit 2.0+, Svelte 5, TypeScript, Tailwind CSS, Lucide Icons  
**DevOps**: Docker, Nginx, Alembic migrations, Pydantic validation

## Getting Started

### Prerequisites

Ensure you have these installed:

- Python 3.10+
- Node.js 18+
- PostgreSQL 13+
- Redis 6+
- Docker (optional — see below)
- Git

### Quick Start (Local Development)

`docker-compose.yml` in this repo only runs Postgres and Redis as containers
— the backend and frontend are not part of it and run directly on the host
(see "Manual Installation" below). This is the fastest way to get the two
stateful dependencies running without installing them natively:

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd rforum
   ```

2. **Create environment configuration:**
   ```bash
   cp .env.example .env
   ```

3. **Start Postgres and Redis:**
   ```bash
   docker compose up -d
   ```

4. **Continue with the backend and frontend setup below.**

### Manual Installation

#### Backend Setup

1. **Clone repository and navigate to project:**
   ```bash
   git clone <repository-url>
   cd rforum
   ```

2. **Create and activate Python virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r app/requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your database and Redis URLs, secret key, etc.
   ```

5. **Set up PostgreSQL database:**
   ```bash
   # Create database
   createdb rforum
   
   # Or using Docker:
   docker run --name rforum-db -e POSTGRES_PASSWORD=rforum \
     -p 5432:5432 -d postgres:15
   ```

6. **Set up Redis:**
   ```bash
   # Using Docker (recommended):
   docker run --name rforum-redis -p 6379:6379 -d redis:7-alpine
   
   # Or install locally:
   # Ubuntu/Debian: sudo apt-get install redis-server
   # macOS: brew install redis
   ```

7. **Run database migrations:**
   ```bash
   cd db
   alembic upgrade head
   cd ..
   ```

8. **Start the backend server:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   Backend will be available at `http://localhost:8000`

#### Frontend Setup

1. **Navigate to frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install Node dependencies:**
   ```bash
   npm install
   ```

3. **Configure development proxy (optional):**
   - Edit `vite.config.ts` to point to your backend URL if different from localhost:8000

4. **Start development server:**
   ```bash
   npm run dev
   ```
   Frontend will be available at `http://localhost:5173`

5. **Build for production (optional):**
   ```bash
   npm run build
   npm run preview  # Preview production build locally
   ```

## Production Deployment

Rforum supports two production deployment methods — there is no full
Docker Compose stack for backend/frontend (`docker-compose.yml` only runs
Postgres/Redis as containers; see "Quick Start" above):

**1. k3s / Helm (recommended for new deployments)** — chart at
[`deploy/helm/rforum/`](./deploy/helm/rforum/) (Traefik Ingress, bundled
Postgres/Redis, cert-manager TLS, Alembic hook). Follow
[`docs/k3s-deploy.md`](./docs/k3s-deploy.md) for install, secrets, optional
Postgres/Redis/uploads restore from a VM backup, and the HTTPS
proxy-header setting that prevents a `/login` mixed-content loop.

**2. Bare-metal** — Uvicorn running directly on the host (per "Manual
Installation" above) behind your own reverse proxy. See
[`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) §9 for the exact proxy
behavior this configuration needs (WebSocket upgrade headers, an 86400s
read timeout on `/ws/`, a 25MB body limit, and serving `frontend/build` as
static files) and "Nginx Configuration" below for where to base your own
config on.

### Environment Configuration for Production

Update your `.env` file with production values:

```env
# Use a strong, randomly generated secret key
SECRET_KEY=your-super-secret-key-here-minimum-32-chars

# Set production PostgreSQL URL
DATABASE_URL=postgresql+asyncpg://user:password@db-host:5432/rforum

# Set production Redis URL
REDIS_URL=redis://:password@redis-host:6379/0

# Update CORS origins for your domain
CORS_ORIGINS=["https://yourdomain.com","https://www.yourdomain.com"]

# Set your invite code
INVITE_CODE=YOUR_CODE

# Optional: Set super admin email for auto-promotion
SUPER_ADMIN_EMAIL=admin@yourdomain.com
```

### Nginx Configuration

There is no bare-metal reverse-proxy `nginx.conf` checked into this repo —
build your own from the behavior documented in
[`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) §9 (TLS termination,
`/api/`+`/ws/` proxying with WebSocket upgrade headers and an 86400s read
timeout, and serving `frontend/build` as static files).

[`frontend/nginx.conf`](./frontend/nginx.conf) is a different, narrower
config: it's baked into the frontend's Docker image (see
`frontend/Dockerfile`) to serve the built static site on its own — used by
the k3s/Helm deployment path, not a reverse proxy for the whole app. If
you're deploying to k3s, use [`docs/k3s-deploy.md`](./docs/k3s-deploy.md)
instead, which routes TLS and `/api`+`/ws` through Traefik (k3s default)
rather than a hand-written reverse-proxy nginx.conf.

## Workflow Guides

### Creating a Session (Moderator)

1. **Register**: Email, password, and invite code
2. **Create Session**: Title, moderator name, speakers, optional event
3. **Add Slides**: Create Poll, Q&A, Feedback, Word Cloud, or Content slides
4. **Upload Assets** (optional): Add supporting documents
5. **Reorder Slides**: Drag to arrange order
6. **Go Live**: Activate and share code with audience
7. **Monitor**: View real-time analytics and responses
8. **End**: Click button, view final analytics

### Joining a Session (Guest)

1. **Get Code**: 8-character code from moderator (no login required)
2. **Enter Code**: Navigate to session in seconds
3. **Participate**: Vote polls, ask/upvote questions, share feedback, submit keywords
4. **Real-time**: Updates appear instantly as moderator advances

### Admin Dashboard (Super Admins)

1. **User Management**: Manage users, assign roles, track activity
2. **Analytics**: Monitor storage and platform metrics
3. **Moderation**: Delete inappropriate content
4. **Session Tracking**: View all platform sessions and events

## Environment Variables Reference

| Variable | Type | Description | Default |
|----------|------|-------------|---------|
| `DATABASE_URL` | String | PostgreSQL connection string | **required** — no default |
| `REDIS_URL` | String | Redis connection string | `redis://redis:6379/0` |
| `SECRET_KEY` | String | JWT signing secret (min 32 chars) | **required** — no default |
| `ALGORITHM` | String | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Integer | Token expiration time | `1440` (24 hours) |
| `INVITE_CODE` | String | Registration invite code | **required** — no default |
| `SUPER_ADMIN_EMAIL` | String | Auto-promote email to super admin on registration | `` (empty — disabled) |
| `SUPER_ADMIN_BOOTSTRAP_TOKEN` | String | Secret also required to auto-promote `SUPER_ADMIN_EMAIL` | `` (empty — disabled) |
| `CORS_ORIGINS` | JSON Array | Allowed CORS origins | **required** — no default |
| `UPLOAD_MAX_MB` | Integer | Max file upload size | `20` |
| `UPLOAD_ALLOWED_EXTENSIONS` | JSON Array or CSV | Allowed file types — accepts either format | `.pdf,.ppt,.pptx,.doc,.docx,.txt,.odp,.odt` |

The app fails to start with a clear error naming any required variable that's missing — see `.env.example` for a working starting point and the "Environment Configuration for Production" section above for production values.



## Notes

**API Documentation**: OpenAPI docs are disabled by default for security. To enable Swagger UI in development, modify `app/main.py`:

```python
app = FastAPI(docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json")
```

## Project Structure

```
rforum/
├── app/              # FastAPI backend (models, routers, auth)
├── frontend/         # SvelteKit frontend (routes, components)
├── db/               # Database migrations (Alembic)
├── deploy/helm/      # k3s/Helm production deployment chart
├── docs/             # Architecture reference and deploy guide
├── docker-compose.yml  # Local dev Postgres + Redis only
└── README.md
```

**Contact**: ajithbm01@gmail.com  
**Report Issues**: [GitHub Issues](https://github.com/ajith4Tech/rforum/issues)

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for complete details.

---
**Made with ❤️ for real-time engagement**
