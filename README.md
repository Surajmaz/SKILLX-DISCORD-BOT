# 🤖 SkillX Discord Bot & Cyberpunk Web Dashboard

A state-of-the-art, prefix-less, AI-powered Discord bot and interactive web dashboard built with **discord.py 2.7+**, **Google Gemini 3.x**, and asynchronous **aiohttp**. Engineered for elite server management, intelligent conversation, proactive moderation, and rich community engagement.

---

## ✨ Features Overview

### ⚡ 1. Prefix-less & Slash System
- **Pure Modern Interaction**: Designed for zero prefix friction — no outdated `!` or `?` required.
- **Full Slash Command Suite**: Clean, auto-completing slash commands across all categories (`/chat`, `/persona`, `/poll`, `/warn`, `/lock`, etc.).
- **Conversational AI Trigger**: Simply mention `@SkillX <prompt>` or reply to any bot message to converse naturally.
- **Direct Keyword Commands**: Common commands run directly (`ping`, `help`, `serverinfo`, `userinfo`).

### 🤖 2. Advanced Gemini 3.x AI Engine
- **Resilient Fallback Chain**: High-availability multi-model chain (`gemini-3.5-flash-lite`, `gemini-3.5-flash`, `gemini-3.1-flash-lite`, `gemini-3.8-flash`).
- **AI Personas (`/persona`)**: Instantly swap AI personalities per user or channel:
  - `default`: Friendly, helpful Discord assistant.
  - `developer`: Senior full-stack engineer producing clean, idiomatic code.
  - `tutor`: Patient, educational explanations using the Feynman technique.
  - `creative`: Expressive, witty, engaging storytelling and brainstorming.
  - `concise`: Ultra-compact, bullet-point precision.
- **Automated Code Review (`/code`)**: Analyzes code snippets for bugs, security vulnerabilities, performance, and best practices.
- **Chat Summarization (`/summarize`)**: Reads and provides clean bullet-point digests of recent channel activity.
- **Conversational Memory**: Threaded multi-turn context awareness with `/clearmemory` management.
- **Smart Markdown Pagination**: Automatically closes and re-opens syntax fences across page splits.

### 🛡️ 3. Proactive AutoMod & Disciplinary Suite
- **Anti-Spam & Flood Shield**: Detects and suppresses rapid message spam (>5 messages in 3 seconds).
- **Anti-Invite Filter**: Auto-deletes unauthorized Discord invite links with instant warnings.
- **Mass-Mention Prevention**: Flags and deletes messages with excessive mentions (>5 tags).
- **Infraction History System**: Persistent JSON disciplinary ledger (`data/infractions.json`) with `/warn`, `/warnings`, and `/clearwarns`.
- **Channel Lockdown Controls**: Emergency `/lock` and `/unlock` to freeze text channels during raids.
- **Slowmode Management**: Dynamic rate regulation (`/slowmode`) from 0 to 6 hours.

### 👥 4. Interactive Community Engagement
- **Live Button Polls (`/poll`)**: Interactive voting with dynamic visual Unicode progress bars and instant vote updates.
- **Automated Giveaways (`/giveaway`)**: Interactive "Join Giveaway" buttons, live entry counts, countdown timer, and automatic winner selection.
- **Timed Reminders (`/remind`)**: Smart async timer alerts with friendly DM/channel notifications.
- **High-Res Avatar Viewer (`/avatar`)**: Fetches full-resolution member and server avatars with direct download links.

### 🔨 5. Comprehensive Moderation Suite
- **Hierarchy Protection**: Safeguards bot owners, moderators, and prevents self-moderation.
- **Interactive Confirmations**: Two-factor UI buttons (`ConfirmView`) for destructive actions (`/kick`, `/ban`).
- **Native Member Timeouts**: Timeout enforcement (`/timeout`) from 1 minute up to 28 days.
- **Non-Destructive Purge**: Bulk message pruning (`/purge`) preserving pinned announcements.

### 📊 6. Utilities & System Diagnostics
- **Dual-Latency Ping (`/ping`)**: Real-time breakdown of WebSocket Gateway and REST API roundtrip with health indicators.
- **Metadata Cards (`/serverinfo`, `/userinfo`, `/botinfo`)**: Beautiful embeds displaying member roles, verification levels, and system resource specs.

---

## 🌐 Cyberpunk Glassmorphic Web Dashboard

A built-in management console running asynchronously on port 8080:

- **6 Real-Time KPI Cards**: Live server count, total members, gateway latency, bot uptime, AI memory contexts, and infractions.
- **Gateway Telemetry Chart**: Live rolling 60-second Chart.js latency visualizer with auto-polling.
- **Live Activity Stream**: Real-time event log recording Discord interactions, moderation events, and AI requests.
- **Interactive Discord Embed Designer**: Visual side-by-side live Discord embed previewer with broadcast delivery to any server channel.
- **In-Browser Gemini AI Studio**: Test AI prompts, change models, tweak temperature, and switch personas directly in your browser.
- **AutoMod Web Console**: Searchable infraction logs with instant one-click web Kick, Ban, and Warn triggers.
- **Live Presence & Cog Manager**: Hot-reload bot extensions without restarting, and change bot status/activity on the fly.
- **Cyber-Aesthetic Login Portal**: Mouse spotlight glow, dynamic canvas particle network, and Web Audio feedback.
- **Enterprise-Grade Security**:
  - HMAC SHA-256 signed session cookies.
  - Cryptographic CSRF token validation on all mutating requests.
  - Brute-force IP rate limiting with automatic cooldowns.
  - Strict Content Security Policy (`CSP`), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.10+
- Discord Bot Token ([Discord Developer Portal](https://discord.com/developers/applications))
- Google Gemini API Key ([Google AI Studio](https://aistudio.google.com/app/apikey))

### 2. Installation

```bash
git clone https://github.com/Surajmaz/SKILLX-DISCORD-BOT.git
cd SKILLX-DISCORD-BOT

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Create or configure `.env`:

```env
DISCORD_TOKEN=your_discord_token_here
GEMINI_API_KEY=your_gemini_api_key_here

# Leave empty for prefix-less mode
COMMAND_PREFIX=

# Optional: Dev Guild ID for instant slash command sync
GUILD_ID=

# Web Dashboard Settings
DASHBOARD_ENABLED=true
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8080
DASHBOARD_PASSWORD=your_secure_password
```

### 4. Running the Bot

```bash
python3 main.py
```

Access the dashboard at `http://localhost:8080`.

---

## 🧪 Testing

Run all unit, integration, and security tests:

```bash
python3 -m unittest discover -s . -p "test_*.py"
```

---

## 📁 Project Architecture

```
├── cogs/
│   ├── ai_chat.py       # Conversational AI, personas, code review & summarizer
│   ├── automod.py       # Anti-spam, invite filter, warn tracking, lock & slowmode
│   ├── community.py     # Live button polls, giveaways, reminders & avatar inspection
│   ├── moderation.py    # Kick, ban, timeout, and purge commands with safety checks
│   └── utility.py       # Ping, serverinfo, userinfo, and botinfo
├── dashboard/
│   ├── app.py           # Aiohttp web server, REST APIs & live event logger
│   ├── security.py      # HMAC sessions, CSRF, rate limiting & security headers
│   └── templates/
│       ├── index.html   # Cyberpunk glassmorphic control center with live telemetry
│       └── login.html   # Animated particle portal with interactive sound effects
├── config.py            # Environment validation & credential management
├── embeds.py            # Discord Embed styling & length bounds
├── gemini_client.py     # Resilient Gemini 3.x asynchronous client with 5 personas
├── main.py              # Bot entrypoint, setup_hook & command tree syncing
├── requirements.txt     # Python dependencies
├── security.py          # Sliding-window rate limiters & input sanitizers
├── ui.py                # Pagination views & confirmation dialogs
├── test_suite.py        # Core bot & utility unit tests
└── test_dashboard.py    # Web dashboard security & API tests
```
