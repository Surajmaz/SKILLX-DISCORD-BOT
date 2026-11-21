# 🤖 SkillX Discord Bot & Cyberpunk Web Dashboard

A state-of-the-art, prefix-less, AI-powered Discord bot and interactive web dashboard built with **discord.py 2.7+**, **Google Gemini 3.x / 2.5 Multi-Tier Fleet**, and asynchronous **aiohttp**. Engineered for elite server management, multilingual real-time translation, proactive moderation, deep community engagement, and enterprise-grade self-healing resilience.

---

## ⚡ Highlights at a Glance

* **Zero-Prefix Modern Interaction**: Slash commands, direct keyword commands, and natural AI conversations via `@SkillX` mentions.
* **🌐 Multilingual AI Translation & Ephemeral Dropdown GUI**: Instant translation of every feature manual, command directory, and message into **25 worldwide languages** using Google Gemini AI, displayed in a private ephemeral menu visible only to the requester.
* **🤖 9-Tier Gemini AI Engine**: Resilient model chain (`gemini-2.5-flash-lite`, `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-3.5-*`) with automatic failover, 503 fast retry, dynamic model cooldowns, and conversational memory.
* **⚡ Multi-Subsystem Stress Tester & Self-Healing Engine**: Real-time load generation benchmarking Event Loop jitter, File I/O throughput (IOPS), Web API concurrency (RPS), and AI failover, backed by an automated `AutoHealingEngine` that reclaims memory, prunes caches, and recalibrates models.
* **💻 Cyberpunk Glassmorphic Web Dashboard**: Full-featured web console with 12 distinct management panels, live telemetry charts, in-browser AI Studio, interactive Discord embed designer, and hot-reloadable cogs.
* **🛡️ Proactive AutoMod & Security**: Anti-spam flood defense, anti-invite filtering, mass-mention suppression, and persistent JSON infraction tracking.
* **🎉 Complete Community & Gaming Suite**: Interactive button polls, automated giveaways, async reminders, leveling with visual XP rank cards, private ticket desk with transcript DM, multi-category trivia, and mini-games.

---

## ✨ Features Overview

### 🌐 1. Multi-Language AI Translation & Ephemeral GUI
- **Universal Feature Translation**: Every feature manual and command guide in `/help` features a `🌐 Translate to Any Language` button.
- **25 Worldwide Languages Supported**:
  - 🇪🇸 Spanish (Español) • 🇫🇷 French (Français) • 🇩🇪 German (Deutsch) • 🇮🇳 Hindi (हिन्दी)
  - 🇯🇵 Japanese (日本語) • 🇨🇳 Simplified Chinese (简体中文) • 🇹🇼 Traditional Chinese (繁體中文)
  - 🇧🇷 Portuguese (Português) • 🇷🇺 Russian (Русский) • 🇸🇦 Arabic (العربية)
  - 🇮🇹 Italian (Italiano) • 🇰🇷 Korean (한국어) • 🇮🇩 Indonesian (Bahasa Indonesia)
  - 🇹🇷 Turkish (Türkçe) • 🇻🇳 Vietnamese (Tiếng Việt) • 🇧🇩 Bengali (বাংলা)
  - 🇵🇭 Tagalog (Filipino) • 🇵🇱 Polish (Polski) • 🇳🇱 Dutch (Nederlands)
  - 🇺🇦 Ukrainian (Українська) • 🇸🇪 Swedish (Svenska) • 🇬🇷 Greek (Ελληνικά)
  - 🇹🇭 Thai (ภาษาไทย) • 🇵🇰 Urdu (اردو) • 🇬🇧 English (Original)
- **Discord Select Menu Dropdown**: Renders custom flag emoji, native name, and regional dialect description matching Discord's native category dropdowns.
- **Private Ephemeral Pop-ups**: Translation selection and translated results are sent with `ephemeral=True` — strictly visible to the requesting user and keeping channels clean.
- **Smart Formatting Preservation**: Retains all Discord markdown syntax (`*`, `**`, `` ` ``, `>`), emojis, parameter tokens (`<user>`, `[intensity]`), and slash command names untouched.
- **In-Memory LRU Translation Cache**: Instant (< 5ms) cached responses on repeated language switches without consuming Gemini API tokens.
- **Universal `/translate` Command**: `/translate text: <text> target_language: <language> [private]` to translate any text or query.
- **Message Context Menu**: Right-click any Discord message → **Apps** → **Translate with Gemini** for instant ephemeral translation.
- **AI Response Translation**: Multi-page AI responses (`PaginatedResponseView`) include a built-in `🌐 Translate` button.

---

### 🤖 2. Advanced Multi-Tier Gemini AI Engine
- **Resilient Fallback Fleet**: Multi-tier priority chain (`gemini-2.5-flash-lite`, `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-3.5-flash-lite`, `gemini-3.5-flash`, `gemini-3.1-flash-lite`, `gemini-3.8-flash`).
- **Dynamic Failover & 503 Auto-Demotion**: Automatic temporary cooldowns on model rate limits or service unavailability, seamlessly failing over to backup models.
- **AI Personas (`/persona`)**: Instantly swap AI personalities per user:
  - `default`: Friendly, intelligent, and helpful Discord assistant.
  - `developer`: Senior full-stack engineer producing idiomatic, bug-free code.
  - `tutor`: Patient educator using the Feynman technique.
  - `creative`: Expressive storyteller and imaginative brainstormer.
  - `concise`: Ultra-compact, bullet-point precision.
  - `sarcastic`: Playfully snarky, witty, and humorous companion.
  - `academic`: Deeply analytical, citation-ready scientific researcher.
- **Automated Code Review (`/code`)**: In-depth analysis checking code syntax, time/space complexity, security vulnerabilities, and optimal refactoring.
- **Chat Summarization (`/summarize`)**: Reads channel conversation logs and returns structured bullet-point executive summaries.
- **Conversational Memory**: Multi-turn context awareness with `/forget` memory reset command.
- **Smart Markdown Pagination**: Automatically closes and re-opens syntax code fences across page splits.

---

### ⚡ 3. System Stress Test & Automated Self-Healing Engine
- **Multi-Dimensional Stress Tester (`stress_test.py`)**:
  - ⏱️ **Event Loop Scheduling**: Concurrent microsecond timer drift analysis measuring average, P95, and maximum jitter.
  - 💾 **Storage & File I/O**: High-throughput atomic JSON read/write persistence benchmarks measuring IOPS and operation latency.
  - 🌐 **Web Dashboard API Concurrency**: Simulated concurrent bursts across internal HTTP endpoints measuring RPS and P95 latency.
  - 🤖 **AI Model Fleet Readiness**: Verification of model chain availability, failover resilience, and response health.
  - 🏆 **Composite Resilience Score**: Computes a weighted 0–100 score and assigns a Resilience Grade (`Grade A+`, `Grade A`, `Grade B`, or `Grade C`).
- **Automated Self-Healing Engine (`AutoHealingEngine`)**:
  - 🧹 **Generational Garbage Collection**: Forces cyclic garbage defragmentation (`gc.collect(2)`) and measures reclaimed RAM.
  - 🎯 **AI Response Cache Pruning**: Evicts expired responses (> 5 min) from memory.
  - 🧠 **Memory Context Pruning**: Defragments idle or empty multi-turn conversation states.
  - 🔄 **Model Fallback Recalibration**: Checks expired cooldowns and restores demoted Gemini models.
  - 🪣 **Rate-Limiter Purge**: Trims dormant sliding-window bucket counters in `security.ai_limiter`.
  - 📜 **Log Buffer Trimming**: Keeps dashboard activity logs strictly bounded in memory.
  - ⚡ **Event Loop Lag Normalization**: Validates microsecond responsiveness post-cleanup.
- **Discord Administration Commands**:
  - `/stresstest [intensity] [auto_heal]` & `!stresstest`: Runs low, medium, or high benchmark directly from Discord.
  - `/autoheal` & `!autoheal`: Executes instant self-healing, memory reclamation, and optimization pass.
- **Web Dashboard Panel (`sec-stresstest`)**: Interactive controls, real-time status indicators, dynamic resilience grade badge, 4 diagnostic cards, manual auto-heal trigger, and automated action report.

---

### 🛡️ 4. Proactive AutoMod & Security Console
- **Anti-Spam & Flood Shield**: Suppresses rapid message spam (> 5 messages in 3 seconds).
- **Anti-Invite Filter**: Auto-deletes unauthorized Discord invite links with instant warnings.
- **Mass-Mention Prevention**: Flags and deletes messages with excessive user/role mentions (> 5 tags).
- **Infraction Ledger**: Persistent JSON disciplinary storage (`data/infractions.json`) with `/warn`, `/warnings`, and `/clearwarns`.
- **Channel Lockdown Controls**: Emergency `/lock` and `/unlock` to freeze text channels during raids.
- **Slowmode Management**: Dynamic rate regulation (`/slowmode`) from 0 to 6 hours.

---

### 👥 5. Community & Engagement Suite
- **Live Button Polls (`/poll`)**: Interactive voting with dynamic visual Unicode progress bars and instant vote updates.
- **Automated Giveaways (`/giveaway`)**: Interactive "Join Giveaway" buttons, live entry counters, countdown timer, and randomized winner draw.
- **Timed Reminders (`/remind`)**: Smart asynchronous timer alerts with friendly DM or channel notifications.
- **High-Res Avatar Viewer (`/avatar`)**: Fetches full-resolution member and server avatars with direct download links.

---

### 🎮 6. Fun, Games & Social Tools
- **Interactive Button Trivia (`/trivia`)**: Multi-category trivia engine (science, history, pop culture, tech) with A/B/C/D Discord buttons, timeout reveals, and score tracking.
- **Classic Games & Predictions**:
  - `/8ball`: 20+ authentic witty Magic 8-ball fortune predictions.
  - `/coinflip`: Heads/tails simulation with coin flips.
  - `/dice`: Customizable polyhedral dice roller (d4, d6, d8, d10, d12, d20, d100).
  - `/rps`: Rock-Paper-Scissors with animated emoji showdowns.
- **Social & Humor**:
  - `/joke` & `/fact`: Large banks of witty jokes and curated educational facts.
  - `/rate`: 0-to-10 rating engine with dynamic tier remarks.
  - `/ship`: Love compatibility calculator with animated Unicode heart progress bars.
  - `/roast` & `/compliment`: Clean lighthearted roasts and genuine compliments.
  - `/mock` & `/reverse`: SpOnGeBoB text converter and string inverter.

---

### 📈 7. Leveling, XP & Server Progression
- **Automated XP Engine**: Grants 15–25 XP per message with 60-second cooldown protection against chat spam.
- **Quadratic Leveling Formula**: `Level N = 5*N² + 50*N + 100` XP curve.
- **Rank Inspection (`/rank`)**: Visual Unicode progress bar card (`▓░`) showing level, total XP, next level target, and guild leaderboard rank.
- **Competitive Leaderboard (`/leaderboard`)**: Top 10 server member ranking with 🥇, 🥈, and 🥉 status podiums.
- **Staff XP Controls**: Administrative `/setxp` and `/resetxp` tools with guild permission guards.

---

### 🎫 8. Support Ticket Desk
- **Interactive Panel Setup (`/ticket-setup`)**: Deploys a persistent channel embed with a "🎫 Open Ticket" Discord button.
- **Private Channel Generation**: Instantly provisions `ticket-{user}-{id}` with isolated view permissions for the opener and staff.
- **Transcript Archiving**: Compiles the last 100 ticket messages into a clean text archive, DMs it to the ticket author, and initiates channel deletion.
- **Ticket Member Management**: Dynamic `/ticket-add` and `/ticket-remove` commands.

---

### 👋 9. Welcome, Farewells & AutoRole
- **Automated Greetings**: Beautiful green-accented (`0x57F287`) embed with user avatar thumbnail, account creation age, and member count footer.
- **Customizable Placeholders**: Full support for `{user}`, `{user.mention}`, `{server}`, and `{member_count}` in `/setwelcome` and `/setgoodbye`.
- **Instant Test Previews**: `/testwelcome` and `/testgoodbye` simulation commands.
- **Join AutoRole (`/autorole`)**: Automatically assigns a default member role upon server entry with role hierarchy checks.

---

### 📋 10. Server Event Audit Logging
- **Dedicated Audit Channel (`/setlogchannel`)**: Live tracking of important server activities.
- **Comprehensive Event Interceptors**:
  - 🗑️ Message Deletions (content, author, channel; ignores bots)
  - ✏️ Message Edits (before / after diff view)
  - 📥 Member Joins (with new-account creation age warning)
  - 📤 Member Departures (with list of previously held roles)
  - 🔨 Member Bans & Unbans (with audit log reason resolution)
  - 🔊 Voice State Updates (channel join, leave, and switch tracking)
  - 🛡️ Role & Nickname Changes

---

### 🔨 11. Comprehensive Moderation Suite
- **Hierarchy Protection**: Safeguards bot owners, moderators, and prevents self-moderation.
- **Interactive Confirmations**: Two-factor UI buttons (`ConfirmView`) for destructive actions (`/kick`, `/ban`).
- **Native Member Timeouts**: Timeout enforcement (`/timeout`) from 1 minute up to 28 days.
- **Non-Destructive Purge**: Bulk message pruning (`/purge`) preserving pinned announcements.

---

### 📊 12. Utilities & System Diagnostics
- **Interactive Command Directory (`/help [category]`)**: Multi-category feature browser with attached `🌐 Translate to Any Language` button.
- **Dual-Latency Ping (`/ping`)**: Real-time breakdown of WebSocket Gateway and REST API roundtrip with health indicators.
- **AI Latency Benchmark (`/aiping`)**: Live generation latency benchmark and active Gemini model tier report.
- **Metadata Cards (`/serverinfo`, `/userinfo`, `/botinfo`)**: Beautiful embeds displaying member roles, verification levels, and system resource specs.

---

## 🌐 Cyberpunk Glassmorphic Web Dashboard

A built-in management console running asynchronously on port 8080:

- **12 Interactive Sections**:
  1. 🏠 **Dashboard Overview**: 8 real-time KPI cards and live Chart.js gateway latency telemetry.
  2. 🤖 **AI Studio & Model Fleet**: Prompt testing, model switching, temperature tweaking, and persona customization.
  3. 📢 **Embed & Broadcast Center**: Side-by-side live Discord embed designer with color clamping security (`0` to `0xFFFFFF`) and channel delivery.
  4. 🌐 **Server Directory Matrix**: Multi-server inspection, member counts, and channel routing.
  5. 🛡️ **AutoMod & Security Console**: Searchable infraction logs with instant one-click web Kick, Ban, and Warn triggers.
  6. 🏆 **Leveling & Leaderboards**: Live global XP progression viewer.
  7. 🎫 **Support Ticket Console**: Real-time ticket stats and channel monitoring.
  8. 👋 **Welcome & AutoRole Config**: In-browser configuration of welcome/farewell channels, messages, and autoroles.
  9. 📜 **Audit & Server Logs**: Real-time activity stream capturing bot events and moderation actions.
  10. 🎯 **Community Engagement Hub**: Web management of active button polls and giveaways.
  11. ⚙️ **Bot Fleet & Cog Settings**: Hot-reload all 10 bot extensions in memory without restarting.
  12. ⚡ **Stress Test & Auto-Healing Console**: Interactive benchmark launcher, score badge, 4 diagnostic telemetry cards, and automated remediation checklist.
- **Zero-Assets Audio Synthesizer**: Web Audio API tone feedback for clicks, success notifications, and warnings.
- **Enterprise-Grade Security**:
  - HMAC SHA-256 signed session cookies.
  - Cryptographic CSRF token validation on all mutating API endpoints.
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

Access the web dashboard at `http://localhost:8080`.

---

## 🧪 Testing

Run the full automated test suite (32 tests covering unit logic, embed bounds, rate limiters, multi-language translation, stress testing, and dashboard security):

```bash
.venv/bin/python3 -m unittest discover -s . -p "test_*.py"
```

---

## 📁 Project Architecture

```
├── cogs/
│   ├── ai_chat.py       # Conversational AI, personas, code review & summarizer
│   ├── automod.py       # Anti-spam, invite filter, warn tracking, lock & slowmode
│   ├── community.py     # Live button polls, giveaways, reminders & avatar inspection
│   ├── fun.py           # Interactive button trivia, 8ball, coinflip, dice, jokes & roasts
│   ├── leveling.py      # XP calculation, rank cards, and guild leaderboards
│   ├── logging_cog.py   # Audit channel logging for messages, members, and voice
│   ├── moderation.py    # Kick, ban, timeout, and purge commands with safety checks
│   ├── tickets.py       # Private channel support tickets with button panel & transcript DM
│   ├── utility.py       # Ping, serverinfo, userinfo, /translate, /stresstest, /autoheal & /help
│   └── welcome.py       # Dynamic welcome/goodbye embeds and join autoroles
├── dashboard/
│   ├── app.py           # Aiohttp web server, REST APIs, stress test & auto-heal routes
│   ├── security.py      # HMAC sessions, CSRF, rate limiting & security headers
│   └── templates/
│       ├── index.html   # Cyberpunk glassmorphic control center with 12 management panels
│       └── login.html   # Animated particle portal with interactive sound effects
├── config.py            # Environment validation & credential management
├── embeds.py            # Discord Embed styling & length bounds
├── gemini_client.py     # Resilient 9-tier Gemini client with translation engine & personas
├── main.py              # Bot entrypoint, setup_hook & command tree syncing
├── requirements.txt     # Python dependencies
├── security.py          # Sliding-window rate limiters & input sanitizers
├── stress_test.py       # Multi-subsystem stress test benchmark & AutoHealingEngine
├── ui.py                # Pagination, LanguageSelectView, HelpMenuView & 25-language catalog
├── test_suite.py        # Core bot, localization, embed & utility unit tests
└── test_dashboard.py    # Web dashboard security, API & stress test tests
```

---

## 📜 License

Distributed under the MIT License. Built with ❤️ by Surajmaz.
