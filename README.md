# 🤖 SkillX Discord Bot

A modern, prefix-less, AI-powered Discord bot built with **discord.py** and **Google Gemini 3.x**, featuring a full suite of administrative moderation tools, utilities, and a secure real-time web dashboard.

---

## ✨ Features

- **⚡ Prefix-less & Slash System**:
  - Full support for Discord application slash commands (`/chat`, `/kick`, `/ping`, `/help`, etc.).
  - Natural conversational AI: simply tag `@SkillX <prompt>`, reply to any bot message, or DM the bot directly to converse.
  - Direct non-prefix command keywords (`ping`, `help`, `serverinfo`, `userinfo`).
  - No legacy `!` or `?` prefixes required.

- **🤖 Google Gemini AI Engine**:
  - Resilient, high-availability model chain with automatic fallback (`gemini-3.5-flash-lite`, `gemini-3.5-flash`, `gemini-3.1-flash-lite`, `gemini-3.8-flash`).
  - Conversational memory context tracking (threaded dialogue).
  - Codeblock-aware pagination for long outputs (automatically closes and re-opens syntax fences across pages).

- **🛡️ Comprehensive Moderation Suite**:
  - Hierarchy protection checks (moderator vs. target, bot vs. target, guild owner safety).
  - Interactive confirmation dialogs (`ConfirmView`) for dangerous actions (`/kick`, `/ban`).
  - Native member timeouts (`/timeout` up to 28 days).
  - Non-destructive bulk message purging (`/purge`, preserving pinned messages).

- **📊 Utilities & Diagnostics**:
  - `/ping`: Dual latency breakdown (WebSocket Gateway + REST API roundtrip with status indicators).
  - `/serverinfo` & `/userinfo`: Rich metadata cards and avatar inspection.
  - `/botinfo`: Uptime counter, active cogs, connected servers, and environment specifications.

- **🌐 Interactive Web Dashboard**:
  - Built-in `aiohttp.web` management server running inside the bot's event loop.
  - Real-time rolling telemetry charts (Chart.js) and system stats.
  - Server directory & live announcement broadcast modal.
  - In-browser Gemini AI test console and memory management.
  - Live presence and status updater (Online, Idle, DND).
  - Security-hardened: HMAC session cookies, CSRF protection, brute-force IP rate limiting, and strict CSP headers.

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

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

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

The Web Dashboard will be available at `http://localhost:8080`.

---

## 🧪 Testing

Run the automated test suite:

```bash
python3 -m unittest test_suite.py test_dashboard.py
```

---

## 📁 Project Structure

```
├── cogs/
│   ├── ai_chat.py       # Conversational AI with memory & mention listeners
│   ├── moderation.py    # Kick, ban, timeout, and purge commands
│   └── utility.py       # Ping, serverinfo, userinfo, and botinfo
├── dashboard/
│   ├── app.py           # Aiohttp web server & REST APIs
│   ├── security.py      # HMAC sessions, CSRF, and rate limiting
│   └── templates/       # Glassmorphic Tailwind web templates
├── config.py            # Environment & credential management
├── embeds.py            # Discord Embed styling & length bounds
├── gemini_client.py     # Resilient Gemini 3.x asynchronous client
├── main.py              # Bot entrypoint & command tree syncing
├── requirements.txt     # Python dependencies
├── security.py          # Sliding-window rate limiters & sanitizers
├── ui.py                # Pagination views & confirmation dialogs
└── test_suite.py        # Automated unit and security tests
```
