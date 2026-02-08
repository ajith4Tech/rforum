# Rforum

**Real-time Audience Engagement Platform**

Rforum is a modern, interactive presentation tool that enables live engagement between moderators and audience members. Create polls, Q&A sessions, and collect feedback in real-time with instant synchronization across all connected devices.

## About

Rforum combines the power of real-time WebSocket communication with a sleek, intuitive interface to transform passive presentations into interactive experiences. Moderators can control presentations and view live responses, while guests join sessions using simple 8-character codes without requiring authentication.

### Key Features

- **Live Polls**: Real-time bar charts that update as your audience votes
- **Q&A Board**: Crowdsource questions with upvoting to surface top questions
- **Feedback Collection**: Gather thoughts and opinions from your entire audience
- **Content Slides**: Display information slides alongside interactive elements
- **No Guest Login Required**: Guests join with a simple session code
- **Real-time Synchronization**: WebSocket-powered instant updates across all connected devices
- **Mobile-Friendly**: Fully responsive design for all screen sizes

## Tech Stack

- **Backend**: FastAPI with Python 3.10+
- **Frontend**: SvelteKit 2.0+ with Svelte 5
- **Database**: PostgreSQL with SQLAlchemy 2.0 ORM
- **Real-time**: WebSockets with Redis pub/sub
- **Styling**: Tailwind CSS
- **Icons**: Lucide Icons
- **Migrations**: Alembic
- **Authentication**: JWT Bearer tokens

## Installation

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 13+
- Redis 6+
- Docker & Docker Compose (optional)

### Backend Setup

1. **Create and activate Python virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r app/requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your database and Redis URLs
   ```

### Frontend Setup

1. **Install Node dependencies:**
   ```bash
   cd frontend
   npm install
   ```

2. **Build frontend (optional for development):**
   ```bash
   npm run build
   ```

### Database Setup

1. **Using Docker Compose (Recommended):**
   ```bash
   docker compose up -d db redis
   ```

2. **Or configure PostgreSQL manually:**
   - Create a PostgreSQL database named `rforum`
   - Update DATABASE_URL in `.env`
   - Set REDIS_URL in `.env`

3. **Run migrations:**
   ```bash
   cd db
   alembic upgrade head
   ```



### Production Mode

1. **Build frontend:**
   ```bash
   cd frontend
   npm run build
   npm run preview
   ```

2. **Run backend:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8001
   ```

## Development Workflow

### Creating a New Session (Moderator)

1. Register or log in to your account
2. Create a new session with a title
3. Add slides (Polls, Q&A, Feedback, or Content slides)
4. Toggle "Go Live" to start the presentation
5. Share the session code with your audience

### Joining a Session (Guest)

1. Open Rforum homepage
2. Enter the 8-character session code
3. View live poll results and submit responses
4. Ask questions and upvote others' questions





## Support & Contributing

For issues, feature requests, or contributions, please refer to the project repository.

## License
