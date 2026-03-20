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
- Docker & Docker Compose (optional, recommended)
- Git

### Quick Start with Docker Compose (Recommended)

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd rforum
   ```

2. **Create environment configuration:**
   ```bash
   cp .env.example .env
   ```

3. **Start all services:**
   ```bash
   docker compose up -d
   ```

4. **Run database migrations:**
   ```bash
   docker compose exec app alembic upgrade head
   ```

5. **Access the application:**
   - Frontend: http://localhost:5173 (development) or http://localhost (production)
   - Backend API: http://localhost:8000/docs (if enabled)

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

### Using Docker Compose

The easiest way to deploy Rforum is with Docker Compose:

1. **Build images:**
   ```bash
   docker compose build
   ```

2. **Start services:**
   ```bash
   docker compose up -d
   ```

3. **Run migrations:**
   ```bash
   docker compose exec app alembic upgrade head
   ```

4. **Access application:**
   - Visit `http://your-server-ip` (configured via Nginx reverse proxy)

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

The project includes Nginx configuration for reverse proxy setup. Edit `nginx/nginx.conf/` to match your domain and SSL certificate paths.

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
| `DATABASE_URL` | String | PostgreSQL connection string | `postgresql+asyncpg://rforum:rforum@db:5432/rforum` |
| `REDIS_URL` | String | Redis connection string | `redis://redis:6379/0` |
| `SECRET_KEY` | String | JWT signing secret (min 32 chars) | `change-me-in-production` |
| `ALGORITHM` | String | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Integer | Token expiration time | `1440` (24 hours) |
| `INVITE_CODE` | String | Registration invite code | `RFORUM01` |
| `SUPER_ADMIN_EMAIL` | String | Auto-promote email to super admin | `` (empty) |
| `CORS_ORIGINS` | JSON Array | Allowed CORS origins | `["http://localhost:5173"]` |
| `UPLOAD_MAX_MB` | Integer | Max file upload size | `20` |
| `UPLOAD_ALLOWED_EXTENSIONS` | String | Allowed file types (CSV) | `.pdf,.ppt,.pptx,.doc,.docx,.txt,.odp,.odt` |



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
├── nginx/            # Reverse proxy configuration
├── docker-compose.yml
└── README.md
```

**Contact**: ajithbm01@gmail.com  
**Report Issues**: [GitHub Issues](https://github.com/ajith4Tech/rforum/issues)

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for complete details.

---
**Made with ❤️ for real-time engagement**
