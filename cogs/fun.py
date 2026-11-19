"""Fun Cog: Games, humor, and entertainment commands for the SkillX Discord Bot."""

import random
import hashlib
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from embeds import base_embed, success_embed, error_embed, info_embed, BRAND_COLOR, AI_COLOR

# ── Colour palette for fun commands ──────────────────────────────────────────
MAGIC_BALL_COLOR   = 0x9B59B6  # Purple
COIN_COLOR         = 0xF1C40F  # Gold
DICE_COLOR         = 0xE67E22  # Orange
RPS_COLOR          = 0x3498DB  # Blue
TRIVIA_COLOR       = 0x1ABC9C  # Teal
FACT_COLOR         = 0x2ECC71  # Green
JOKE_COLOR         = 0xE91E63  # Pink
RATE_COLOR         = 0x9B59B6  # Amethyst
SHIP_COLOR         = 0xE74C3C  # Red / Love
ROAST_COLOR        = 0xE74C3C  # Fire red
COMPLIMENT_COLOR   = 0xFF69B4  # Hot pink
MEME_COLOR         = 0x7289DA  # Blurple-ish
ASCII_COLOR        = 0x607D8B  # Slate
TEXT_FUN_COLOR      = 0x00BCD4  # Cyan

# ── 8-Ball responses (20+) ──────────────────────────────────────────────────
EIGHT_BALL_RESPONSES = [
    "It is certain. 🌟", "It is decidedly so.", "Without a doubt!",
    "Yes — definitely.", "You may rely on it.", "As I see it, yes.",
    "Most likely.", "Outlook good!", "Yes! 🎉", "Signs point to yes.",
    "Reply hazy, try again… 🌫️", "Ask again later.", "Better not tell you now.",
    "Cannot predict now.", "Concentrate and ask again. 🔮",
    "Don't count on it. 😬", "My reply is no.", "My sources say no.",
    "Outlook not so good.", "Very doubtful. 😕",
    "Absolutely! No question about it! 🔥",
    "The stars say… maybe. ⭐", "I wouldn't bet on it, chief. 💀",
    "Ask your mom. She knows everything. 👩",
]

# ── Trivia bank (30+ questions) ─────────────────────────────────────────────
TRIVIA_QUESTIONS = [
    # Science
    {"category": "🔬 Science", "q": "What planet is known as the Red Planet?", "options": ["Venus", "Mars", "Jupiter", "Saturn"], "answer": 1},
    {"category": "🔬 Science", "q": "What is the chemical symbol for gold?", "options": ["Go", "Gd", "Au", "Ag"], "answer": 2},
    {"category": "🔬 Science", "q": "How many bones are in the adult human body?", "options": ["186", "206", "226", "256"], "answer": 1},
    {"category": "🔬 Science", "q": "What gas do plants absorb from the atmosphere?", "options": ["Oxygen", "Nitrogen", "Carbon Dioxide", "Hydrogen"], "answer": 2},
    {"category": "🔬 Science", "q": "What is the speed of light approximately?", "options": ["300,000 km/s", "150,000 km/s", "500,000 km/s", "1,000,000 km/s"], "answer": 0},
    {"category": "🔬 Science", "q": "What is the powerhouse of the cell?", "options": ["Nucleus", "Ribosome", "Mitochondria", "Golgi apparatus"], "answer": 2},
    {"category": "🔬 Science", "q": "What element has the atomic number 1?", "options": ["Helium", "Hydrogen", "Lithium", "Oxygen"], "answer": 1},
    {"category": "🔬 Science", "q": "What is the largest organ in the human body?", "options": ["Liver", "Brain", "Skin", "Heart"], "answer": 2},
    # History
    {"category": "📜 History", "q": "In what year did World War II end?", "options": ["1943", "1944", "1945", "1946"], "answer": 2},
    {"category": "📜 History", "q": "Who was the first President of the United States?", "options": ["John Adams", "Thomas Jefferson", "George Washington", "Ben Franklin"], "answer": 2},
    {"category": "📜 History", "q": "The Great Wall of China was primarily built to protect against whom?", "options": ["Japanese", "Mongols", "Koreans", "Vikings"], "answer": 1},
    {"category": "📜 History", "q": "What ancient civilization built the Machu Picchu complex?", "options": ["Aztecs", "Mayans", "Incas", "Olmecs"], "answer": 2},
    {"category": "📜 History", "q": "In which year did the Titanic sink?", "options": ["1910", "1912", "1914", "1916"], "answer": 1},
    {"category": "📜 History", "q": "Who painted the Mona Lisa?", "options": ["Michelangelo", "Raphael", "Leonardo da Vinci", "Donatello"], "answer": 2},
    {"category": "📜 History", "q": "What was the longest war in history?", "options": ["Hundred Years' War", "335 Years' War", "Thirty Years' War", "Seven Years' War"], "answer": 1},
    {"category": "📜 History", "q": "Which empire was ruled by Genghis Khan?", "options": ["Ottoman", "Roman", "Mongol", "Persian"], "answer": 2},
    # Pop Culture
    {"category": "🎬 Pop Culture", "q": "What is the highest-grossing film of all time (unadjusted)?", "options": ["Avengers: Endgame", "Avatar", "Titanic", "Star Wars: TFA"], "answer": 1},
    {"category": "🎬 Pop Culture", "q": "Which band performed 'Bohemian Rhapsody'?", "options": ["The Beatles", "Led Zeppelin", "Queen", "Pink Floyd"], "answer": 2},
    {"category": "🎬 Pop Culture", "q": "What fictional country is Black Panther from?", "options": ["Genovia", "Wakanda", "Latveria", "Zamunda"], "answer": 1},
    {"category": "🎬 Pop Culture", "q": "Who played Jack in the movie Titanic?", "options": ["Brad Pitt", "Leonardo DiCaprio", "Johnny Depp", "Tom Hanks"], "answer": 1},
    {"category": "🎬 Pop Culture", "q": "What is the name of Harry Potter's owl?", "options": ["Errol", "Pigwidgeon", "Hedwig", "Scabbers"], "answer": 2},
    {"category": "🎬 Pop Culture", "q": "Which TV show features a character named Walter White?", "options": ["The Wire", "Breaking Bad", "Better Call Saul", "Ozark"], "answer": 1},
    {"category": "🎬 Pop Culture", "q": "Who wrote the 'Harry Potter' book series?", "options": ["Suzanne Collins", "J.R.R. Tolkien", "J.K. Rowling", "Stephen King"], "answer": 2},
    {"category": "🎬 Pop Culture", "q": "In 'The Matrix', what color pill does Neo take?", "options": ["Blue", "Red", "Green", "Yellow"], "answer": 1},
    # Tech
    {"category": "💻 Tech", "q": "What does 'HTTP' stand for?", "options": ["HyperText Transfer Protocol", "High Tech Transfer Protocol", "HyperText Transit Path", "Home Tool Transfer Protocol"], "answer": 0},
    {"category": "💻 Tech", "q": "Who co-founded Apple with Steve Jobs?", "options": ["Bill Gates", "Steve Wozniak", "Elon Musk", "Mark Zuckerberg"], "answer": 1},
    {"category": "💻 Tech", "q": "What programming language is known as the 'language of the web'?", "options": ["Python", "Java", "JavaScript", "C++"], "answer": 2},
    {"category": "💻 Tech", "q": "What year was the first iPhone released?", "options": ["2005", "2006", "2007", "2008"], "answer": 2},
    {"category": "💻 Tech", "q": "What does 'CPU' stand for?", "options": ["Central Process Unit", "Central Processing Unit", "Computer Personal Unit", "Central Program Utility"], "answer": 1},
    {"category": "💻 Tech", "q": "Which company developed the Python programming language?", "options": ["Google", "Microsoft", "It was a personal project by Guido van Rossum", "Sun Microsystems"], "answer": 2},
    {"category": "💻 Tech", "q": "What does 'RAM' stand for?", "options": ["Random Access Memory", "Read Access Memory", "Run Active Module", "Rapid Access Module"], "answer": 0},
    {"category": "💻 Tech", "q": "What is the name of Linux's mascot?", "options": ["Beastie", "Tux", "Wilber", "Konqi"], "answer": 1},
]

# ── Fun facts (40+) ─────────────────────────────────────────────────────────
FUN_FACTS = [
    "Honey never spoils. Archaeologists found 3,000-year-old honey in Egyptian tombs that was still edible!",
    "Octopuses have three hearts and blue blood. 🐙",
    "A group of flamingos is called a 'flamboyance'. 🦩",
    "Bananas are berries, but strawberries aren't. 🍌",
    "The shortest war in history lasted 38 to 45 minutes (Anglo-Zanzibar War, 1896).",
    "Venus is the only planet that spins clockwise. 🌍",
    "A bolt of lightning is five times hotter than the surface of the sun. ⚡",
    "There are more possible iterations of a game of chess than atoms in the observable universe. ♟️",
    "The inventor of the Pringles can is buried in one. 🥔",
    "Cows have best friends and get stressed when separated. 🐄",
    "The unicorn is the national animal of Scotland. 🦄",
    "An octopus has nine brains — one central and one in each arm.",
    "Wombat poop is cube-shaped. 💩",
    "The Eiffel Tower can grow up to 6 inches taller during summer due to thermal expansion.",
    "A jiffy is an actual unit of time: 1/100th of a second.",
    "The world's largest desert is Antarctica, not the Sahara.",
    "Humans share about 60% of their DNA with bananas. 🧬",
    "It rains diamonds on Saturn and Jupiter. 💎",
    "A day on Venus is longer than its year.",
    "There are more trees on Earth than stars in the Milky Way. 🌳",
    "Oxford University is older than the Aztec Empire.",
    "The total weight of ants on Earth roughly equals the total weight of humans.",
    "Cleopatra lived closer in time to the Moon landing than to the building of the Great Pyramid.",
    "Nintendo was founded in 1889 as a playing card company. 🎴",
    "Hot water freezes faster than cold water (Mpemba effect). 🧊",
    "A group of porcupines is called a 'prickle'. 🦔",
    "The Great Wall of China is not visible from space with the naked eye.",
    "Your brain uses about 20% of your body's total energy. 🧠",
    "Sharks existed before trees. 🦈",
    "The moon has moonquakes. 🌙",
    "Space smells like seared steak and gunpowder, according to astronauts. 🚀",
    "A cloud can weigh more than a million pounds. ☁️",
    "Sloths can hold their breath longer than dolphins — up to 40 minutes! 🦥",
    "The longest hiccuping spree lasted 68 years.",
    "A blue whale's heart is so big, a small child could swim through its arteries. 🐋",
    "Cats have over 20 vocalizations, including the purr. 🐱",
    "There's a species of jellyfish that is biologically immortal. 🪼",
    "Every two minutes, we take more photos than all of humanity did in the 1800s. 📸",
    "The first computer bug was an actual real bug — a moth found in a Harvard computer in 1947. 🐛",
    "Koalas sleep up to 22 hours per day. 🐨",
    "Astronauts grow up to 2 inches taller in space. 🧑‍🚀",
    "Honey bees can recognize human faces. 🐝",
]

# ── Jokes (30+) ──────────────────────────────────────────────────────────────
JOKES = [
    {"setup": "Why don't scientists trust atoms?", "punchline": "Because they make up everything! 😂"},
    {"setup": "Why did the scarecrow win an award?", "punchline": "He was outstanding in his field! 🌾"},
    {"setup": "I told my wife she was drawing her eyebrows too high.", "punchline": "She looked surprised. 😮"},
    {"setup": "What do you call a fake noodle?", "punchline": "An impasta! 🍝"},
    {"setup": "Why don't eggs tell jokes?", "punchline": "They'd crack each other up! 🥚"},
    {"setup": "What do you call a bear with no teeth?", "punchline": "A gummy bear! 🧸"},
    {"setup": "I'm reading a book about anti-gravity.", "punchline": "It's impossible to put down! 📖"},
    {"setup": "Why did the math book look so sad?", "punchline": "Because it had too many problems. 📐"},
    {"setup": "What do you call a fish without eyes?", "punchline": "A fsh. 🐟"},
    {"setup": "Why do programmers prefer dark mode?", "punchline": "Because light attracts bugs! 🐛"},
    {"setup": "What's a computer's favorite snack?", "punchline": "Microchips! 💻"},
    {"setup": "Why do Java developers wear glasses?", "punchline": "Because they can't C#! 🤓"},
    {"setup": "How does a penguin build its house?", "punchline": "Igloos it together! 🐧"},
    {"setup": "What do you call a lazy kangaroo?", "punchline": "A pouch potato! 🦘"},
    {"setup": "Why can't a bicycle stand on its own?", "punchline": "Because it's two-tired! 🚲"},
    {"setup": "I used to hate facial hair…", "punchline": "But then it grew on me. 🧔"},
    {"setup": "What did the ocean say to the beach?", "punchline": "Nothing, it just waved. 🌊"},
    {"setup": "Why don't skeletons fight each other?", "punchline": "They don't have the guts! 💀"},
    {"setup": "What do you call a sleeping dinosaur?", "punchline": "A dino-snore! 🦖"},
    {"setup": "How do you organize a space party?", "punchline": "You planet! 🪐"},
    {"setup": "Why did the coffee file a police report?", "punchline": "It got mugged! ☕"},
    {"setup": "What did one wall say to the other wall?", "punchline": "I'll meet you at the corner! 🧱"},
    {"setup": "Why do cows wear bells?", "punchline": "Because their horns don't work! 🐮"},
    {"setup": "What do you get when you cross a snowman and a vampire?", "punchline": "Frostbite! 🧛"},
    {"setup": "I'm on a seafood diet.", "punchline": "I see food and I eat it. 🦐"},
    {"setup": "What do you call cheese that isn't yours?", "punchline": "Nacho cheese! 🧀"},
    {"setup": "Why did the golfer bring two pairs of pants?", "punchline": "In case he got a hole in one! ⛳"},
    {"setup": "What's orange and sounds like a parrot?", "punchline": "A carrot! 🥕"},
    {"setup": "How do trees access the internet?", "punchline": "They log in! 🌲"},
    {"setup": "What did the grape do when it got stepped on?", "punchline": "Nothing, it just let out a little wine! 🍇"},
    {"setup": "Why don't oysters share their pearls?", "punchline": "Because they're shellfish! 🦪"},
]

# ── Rate tiers ───────────────────────────────────────────────────────────────
RATE_COMMENTS = {
    0:  "Yikes… absolute zero. Even my circuits cringed. 🥶",
    1:  "One out of ten? That's just sad. Like a soggy sandwich. 🥪",
    2:  "Barely registers on the scale. 😬",
    3:  "Meh. It exists, I guess. 🤷",
    4:  "Below average, like a Monday morning. 😐",
    5:  "Perfectly mediocre. The beige of ratings. 😶",
    6:  "Not bad! Slightly above 'whatever'. 👍",
    7:  "Pretty solid! Like a good pizza slice. 🍕",
    8:  "Now we're talking! Top-tier material. 🔥",
    9:  "Almost perfect! *Chef's kiss.* 👨‍🍳💋",
    10: "ELEVEN OUT OF TEN — wait, 10/10! Perfection! 🏆✨",
}

# ── Ship commentary ──────────────────────────────────────────────────────────
SHIP_COMMENTS = {
    (0, 20):   "💔 Yikes… the universe said no. Hard pass.",
    (20, 40):  "😕 It's giving 'just friends' energy. Maybe in another timeline.",
    (40, 60):  "🤔 There's potential here… but it needs work. Like a lot of work.",
    (60, 75):  "😊 Not bad! There's a spark — could go either way!",
    (75, 90):  "😍 Ooh la la! The chemistry is REAL. Ship it!",
    (90, 101): "💕 SOULMATES! Someone write the fanfic already! 💍",
}

# ── Roasts (20+, lighthearted) ───────────────────────────────────────────────
ROASTS = [
    "You bring everyone so much joy… when you leave the room. 🚪",
    "I'd agree with you, but then we'd both be wrong. 🤷",
    "You're proof that even AI can have bad taste in friends. 🤖",
    "You're like a cloud — everything brightens up when you disappear. ☁️",
    "If you were any more basic, you'd be a pH of 14. 🧪",
    "You're not stupid; you just have bad luck thinking. 🧠",
    "I'd roast you harder, but I don't want to burn the whole server. 🔥",
    "You're the reason they invented the mute button. 🔇",
    "If laughter is the best medicine, your face must be curing the world. 😂",
    "You're like a software update — nobody wants you, but we're stuck with you. 💾",
    "You have something on your chin… no, the third one. 😏",
    "You're the human equivalent of a participation trophy. 🏅",
    "You're not useless — you can always serve as a bad example! 📋",
    "Light travels faster than sound, which is why you seemed bright until you spoke. 💡",
    "If I had a dollar for every smart thing you said, I'd be broke. 💸",
    "You're like a penny — two-faced and not worth much. 🪙",
    "I'm not saying you're basic, but your pH level is 14. 🧫",
    "You're like a screen door on a submarine — not very useful. 🚢",
    "If ignorance is bliss, you must be the happiest person alive. 😇",
    "You're the reason God created the middle finger. 🖕",
    "You're proof that evolution can go in reverse. 🐒",
    "You're about as useful as the 'ueue' in 'queue'. 📝",
]

# ── Compliments (20+) ────────────────────────────────────────────────────────
COMPLIMENTS = [
    "You light up every room you walk into! ✨",
    "Your smile is contagious — seriously, it should come with a warning label. 😄",
    "You have the best energy and everyone can feel it! 💫",
    "You're the kind of person everyone needs in their life. 💖",
    "Your creativity knows no bounds! 🎨",
    "You make the world a better place just by being in it. 🌍",
    "You're basically a human ray of sunshine. ☀️",
    "If kindness were a currency, you'd be a billionaire. 💰",
    "You're one in a million — actually, one in seven billion. 🌟",
    "Your vibe is immaculate. Keep doing you! 💅",
    "You're the friend everyone wishes they had. 🤗",
    "You have a heart of gold and a mind of diamonds. 💎",
    "Even on your worst day, you're still pretty amazing. 🏆",
    "You could make a grumpy cat smile. 🐱",
    "The world needs more people like you. Period. 🙌",
    "You're stronger than you think and braver than you believe. 💪",
    "Your laugh is literally the best sound in the universe. 🎵",
    "You deserve all the good things coming your way. 🎁",
    "You're smarter than Google and cooler than Alexa. 🤖",
    "If awesome were a job, you'd be CEO. 👔",
    "You make ordinary moments extraordinary. ⭐",
    "You are a vibe. That's it. That's the compliment. 😎",
]

# ── Meme templates (text-based) ──────────────────────────────────────────────
MEME_TEMPLATES = [
    {"title": "Distracted Boyfriend", "desc": "Me → {new shiny thing}\nMy responsibilities → standing there like 😤\nMy deadlines → 👀"},
    {"title": "Drake Hotline Bling", "desc": "❌ Doing the assignment on time\n✅ Starting it at 3 AM the night before"},
    {"title": "This Is Fine 🔥🐕", "desc": "*Everything is on fire*\nMe: 'This is fine. I'm okay with the events that are unfolding currently.'"},
    {"title": "Expanding Brain", "desc": "🧠 Using Google\n🧠✨ Using Stack Overflow\n🧠💫 Asking ChatGPT\n🧠🌌 Randomly changing things until it works"},
    {"title": "One Does Not Simply", "desc": "One does not simply… close VS Code after 'just one more fix'. 💻"},
    {"title": "Surprised Pikachu", "desc": "*Stays up till 4 AM*\n*Feels tired the next day*\n😮⚡ Surprised Pikachu"},
    {"title": "Stonks 📈", "desc": "When you find a $5 bill in your old jacket pocket:\n📈 S T O N K S"},
    {"title": "Is This a Pigeon? 🦋", "desc": "Anime character: *points at a clearly obvious thing*\n'Is this a {completely wrong thing}?'"},
    {"title": "Two Buttons", "desc": "Button 1: Sleep early and be productive\nButton 2: One more episode\n*sweating intensifies* 😰"},
    {"title": "Change My Mind", "desc": "☕ *sits at table*\n'Tabs are better than spaces'\nChange my mind."},
    {"title": "Monkey Puppet 🐵", "desc": "*When someone mentions that bug you said you fixed last week*\n🐵👀 *looks away nervously*"},
    {"title": "Galaxy Brain", "desc": "Normal: Reading documentation\nEnlightened: Reading source code\nAscended: Trial and error\nGalaxy Brain: Asking in Discord 🌌"},
]

# ── ASCII block letters ──────────────────────────────────────────────────────
ASCII_LETTERS = {
    'A': ["  #  ", " # # ", "#####", "#   #", "#   #"],
    'B': ["#### ", "#   #", "#### ", "#   #", "#### "],
    'C': [" ####", "#    ", "#    ", "#    ", " ####"],
    'D': ["#### ", "#   #", "#   #", "#   #", "#### "],
    'E': ["#####", "#    ", "###  ", "#    ", "#####"],
    'F': ["#####", "#    ", "###  ", "#    ", "#    "],
    'G': [" ####", "#    ", "# ###", "#   #", " ####"],
    'H': ["#   #", "#   #", "#####", "#   #", "#   #"],
    'I': ["#####", "  #  ", "  #  ", "  #  ", "#####"],
    'J': ["#####", "   # ", "   # ", "#  # ", " ##  "],
    'K': ["#   #", "#  # ", "###  ", "#  # ", "#   #"],
    'L': ["#    ", "#    ", "#    ", "#    ", "#####"],
    'M': ["#   #", "## ##", "# # #", "#   #", "#   #"],
    'N': ["#   #", "##  #", "# # #", "#  ##", "#   #"],
    'O': [" ### ", "#   #", "#   #", "#   #", " ### "],
    'P': ["#### ", "#   #", "#### ", "#    ", "#    "],
    'Q': [" ### ", "#   #", "# # #", "#  ##", " ####"],
    'R': ["#### ", "#   #", "#### ", "#  # ", "#   #"],
    'S': [" ####", "#    ", " ### ", "    #", "#### "],
    'T': ["#####", "  #  ", "  #  ", "  #  ", "  #  "],
    'U': ["#   #", "#   #", "#   #", "#   #", " ### "],
    'V': ["#   #", "#   #", "#   #", " # # ", "  #  "],
    'W': ["#   #", "#   #", "# # #", "## ##", "#   #"],
    'X': ["#   #", " # # ", "  #  ", " # # ", "#   #"],
    'Y': ["#   #", " # # ", "  #  ", "  #  ", "  #  "],
    'Z': ["#####", "   # ", "  #  ", " #   ", "#####"],
    '0': [" ### ", "#  ##", "# # #", "##  #", " ### "],
    '1': ["  #  ", " ##  ", "  #  ", "  #  ", "#####"],
    '2': [" ### ", "#   #", "  ## ", " #   ", "#####"],
    '3': [" ### ", "#   #", "  ## ", "#   #", " ### "],
    '4': ["#   #", "#   #", "#####", "    #", "    #"],
    '5': ["#####", "#    ", "#### ", "    #", "#### "],
    '6': [" ### ", "#    ", "#### ", "#   #", " ### "],
    '7': ["#####", "   # ", "  #  ", " #   ", "#    "],
    '8': [" ### ", "#   #", " ### ", "#   #", " ### "],
    '9': [" ### ", "#   #", " ####", "    #", " ### "],
    ' ': ["     ", "     ", "     ", "     ", "     "],
    '!': ["  #  ", "  #  ", "  #  ", "     ", "  #  "],
    '?': [" ### ", "#   #", "  ## ", "     ", "  #  "],
}

VALID_DICE_SIDES = {4, 6, 8, 10, 12, 20, 100}


# ═════════════════════════════════════════════════════════════════════════════
#  Trivia View (interactive buttons)
# ═════════════════════════════════════════════════════════════════════════════

class PunchlineButton(discord.ui.View):
    """A single button that reveals a joke's punchline."""

    def __init__(self, punchline: str):
        super().__init__(timeout=30)
        self.punchline = punchline

    @discord.ui.button(label="Reveal Punchline 👀", style=discord.ButtonStyle.primary)
    async def reveal(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.label = "Punchline Revealed!"
        button.style = discord.ButtonStyle.secondary
        button.disabled = True
        self.stop()
        embed = base_embed(
            title="🤣 Punchline",
            description=self.punchline,
            color=JOKE_COLOR,
        )
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(embed=embed, ephemeral=True)


class TriviaView(discord.ui.View):
    """Interactive trivia with A/B/C/D buttons. Tracks answers and reveals the correct one."""

    LABELS = ["A", "B", "C", "D"]
    STYLES = [
        discord.ButtonStyle.primary,
        discord.ButtonStyle.primary,
        discord.ButtonStyle.primary,
        discord.ButtonStyle.primary,
    ]

    def __init__(self, question: dict, scores: dict):
        super().__init__(timeout=15)
        self.question = question
        self.scores = scores
        self.answered: set[int] = set()  # user IDs who answered
        self.correct_index: int = question["answer"]

        for i, option_text in enumerate(question["options"]):
            button = discord.ui.Button(
                label=f"{self.LABELS[i]}: {option_text}",
                style=self.STYLES[i],
                custom_id=f"trivia_{i}",
            )
            button.callback = self._make_callback(i)
            self.add_item(button)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            user_id = interaction.user.id
            if user_id in self.answered:
                await interaction.response.send_message("You already answered! ⏳", ephemeral=True)
                return
            self.answered.add(user_id)
            correct = index == self.correct_index
            if correct:
                self.scores[user_id] = self.scores.get(user_id, 0) + 1
                await interaction.response.send_message(
                    f"✅ Correct! Your score: **{self.scores[user_id]}**", ephemeral=True
                )
            else:
                correct_text = self.question["options"][self.correct_index]
                await interaction.response.send_message(
                    f"❌ Wrong! The answer was **{self.LABELS[self.correct_index]}: {correct_text}**. "
                    f"Your score: **{self.scores.get(user_id, 0)}**",
                    ephemeral=True,
                )
        return callback

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
                idx_str = child.custom_id.split("_")[-1] if child.custom_id else ""
                if idx_str.isdigit() and int(idx_str) == self.correct_index:
                    child.style = discord.ButtonStyle.success
                else:
                    child.style = discord.ButtonStyle.secondary
        # Try to edit the message if possible
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# ═════════════════════════════════════════════════════════════════════════════
#  Fun Cog
# ═════════════════════════════════════════════════════════════════════════════

class Fun(commands.Cog, name="Fun"):
    """Games, humour, and entertainment for every occasion. 🎉"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.trivia_scores: dict[int, int] = {}  # user_id -> score (in-memory)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _ship_percent(id1: int, id2: int) -> int:
        """Deterministic love % from two user IDs (order-independent)."""
        pair = tuple(sorted((id1, id2)))
        h = hashlib.md5(f"{pair}".encode()).hexdigest()
        return int(h, 16) % 101

    @staticmethod
    def _progress_bar(pct: int, length: int = 10) -> str:
        filled = round(pct / 100 * length)
        return "█" * filled + "░" * (length - filled)

    @staticmethod
    def _text_to_ascii(text: str) -> str:
        text = text.upper()[:10]  # limit to 10 chars
        rows: list[str] = [""] * 5
        for ch in text:
            letter = ASCII_LETTERS.get(ch, ASCII_LETTERS.get(' '))
            if letter is None:
                letter = ASCII_LETTERS[' ']
            for r in range(5):
                rows[r] += letter[r] + " "
        return "\n".join(rows)

    @staticmethod
    def _mock_text(text: str) -> str:
        return "".join(
            ch.upper() if i % 2 == 0 else ch.lower()
            for i, ch in enumerate(text)
        )

    # ═════════════════════════════════════════════════════════════════════════
    #  1. 8-BALL
    # ═════════════════════════════════════════════════════════════════════════

    def _build_8ball_embed(self, question: str, user: discord.User) -> discord.Embed:
        answer = random.choice(EIGHT_BALL_RESPONSES)
        embed = base_embed(title="🎱 Magic 8-Ball", color=MAGIC_BALL_COLOR, user=user)
        embed.add_field(name="❓ Question", value=question[:1024], inline=False)
        embed.add_field(name="🔮 Answer", value=f"**{answer}**", inline=False)
        return embed

    @app_commands.command(name="8ball", description="Ask the Magic 8-Ball a question")
    @app_commands.describe(question="Your burning question")
    async def eightball_slash(self, interaction: discord.Interaction, question: str):
        await interaction.response.send_message(
            embed=self._build_8ball_embed(question, interaction.user)
        )

    @commands.command(name="8ball", aliases=["eightball", "magic8ball"], help="Ask the Magic 8-Ball a question.")
    async def eightball_prefix(self, ctx: commands.Context, *, question: str):
        await ctx.reply(embed=self._build_8ball_embed(question, ctx.author), mention_author=False)

    # ═════════════════════════════════════════════════════════════════════════
    #  2. COINFLIP
    # ═════════════════════════════════════════════════════════════════════════

    def _build_coinflip_embed(self, user: discord.User) -> discord.Embed:
        result = random.choice(["Heads", "Tails"])
        emoji = "🪙" if result == "Heads" else "🪙"
        embed = base_embed(
            title=f"{emoji} Coin Flip",
            description=f"The coin spins through the air and lands on…\n\n# **{result}!**",
            color=COIN_COLOR,
            user=user,
        )
        return embed

    @app_commands.command(name="coinflip", description="Flip a coin — heads or tails!")
    async def coinflip_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self._build_coinflip_embed(interaction.user))

    @commands.command(name="coinflip", aliases=["flip", "coin"], help="Flip a coin — heads or tails!")
    async def coinflip_prefix(self, ctx: commands.Context):
        await ctx.reply(embed=self._build_coinflip_embed(ctx.author), mention_author=False)

    # ═════════════════════════════════════════════════════════════════════════
    #  3. DICE
    # ═════════════════════════════════════════════════════════════════════════

    def _build_dice_embed(self, sides: int, user: discord.User) -> discord.Embed:
        result = random.randint(1, sides)
        crit = ""
        if sides == 20:
            if result == 20:
                crit = "\n🌟 **NATURAL 20! CRITICAL HIT!** 🌟"
            elif result == 1:
                crit = "\n💀 **NATURAL 1! CRITICAL FAIL!** 💀"
        embed = base_embed(
            title="🎲 Dice Roll",
            description=f"Rolling a **d{sides}**…\n\n# 🎯 **{result}**{crit}",
            color=DICE_COLOR,
            user=user,
        )
        return embed

    @app_commands.command(name="dice", description="Roll a dice (d4, d6, d8, d10, d12, d20, d100)")
    @app_commands.describe(sides="Number of sides (default: 6)")
    async def dice_slash(self, interaction: discord.Interaction, sides: int = 6):
        if sides not in VALID_DICE_SIDES:
            await interaction.response.send_message(
                embed=error_embed("Invalid Dice", f"Choose from: {', '.join(f'd{s}' for s in sorted(VALID_DICE_SIDES))}"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(embed=self._build_dice_embed(sides, interaction.user))

    @commands.command(name="dice", aliases=["roll", "d"], help="Roll a dice (d4/d6/d8/d10/d12/d20/d100).")
    async def dice_prefix(self, ctx: commands.Context, sides: int = 6):
        if sides not in VALID_DICE_SIDES:
            await ctx.reply(
                embed=error_embed("Invalid Dice", f"Choose from: {', '.join(f'd{s}' for s in sorted(VALID_DICE_SIDES))}"),
                mention_author=False,
            )
            return
        await ctx.reply(embed=self._build_dice_embed(sides, ctx.author), mention_author=False)

    # ═════════════════════════════════════════════════════════════════════════
    #  4. ROCK PAPER SCISSORS
    # ═════════════════════════════════════════════════════════════════════════

    RPS_EMOJI = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
    RPS_WINS  = {"rock": "scissors", "paper": "rock", "scissors": "paper"}

    def _build_rps_embed(self, user_choice: str, user: discord.User) -> Optional[discord.Embed]:
        choice = user_choice.lower().strip()
        if choice not in self.RPS_EMOJI:
            return None
        bot_choice = random.choice(list(self.RPS_EMOJI.keys()))
        user_emoji = self.RPS_EMOJI[choice]
        bot_emoji = self.RPS_EMOJI[bot_choice]

        if choice == bot_choice:
            result = "🤝 It's a **tie**!"
            color = COIN_COLOR
        elif self.RPS_WINS[choice] == bot_choice:
            result = "🎉 You **win**!"
            color = 0x2ECC71
        else:
            result = "😈 I **win**!"
            color = 0xE74C3C

        embed = base_embed(title="Rock Paper Scissors", color=color, user=user)
        embed.add_field(name="You", value=f"{user_emoji} {choice.title()}", inline=True)
        embed.add_field(name="⚔️ VS", value="—", inline=True)
        embed.add_field(name="Bot", value=f"{bot_emoji} {bot_choice.title()}", inline=True)
        embed.add_field(name="Result", value=result, inline=False)
        return embed

    @app_commands.command(name="rps", description="Play Rock Paper Scissors against the bot!")
    @app_commands.describe(choice="rock, paper, or scissors")
    @app_commands.choices(choice=[
        app_commands.Choice(name="🪨 Rock", value="rock"),
        app_commands.Choice(name="📄 Paper", value="paper"),
        app_commands.Choice(name="✂️ Scissors", value="scissors"),
    ])
    async def rps_slash(self, interaction: discord.Interaction, choice: str):
        embed = self._build_rps_embed(choice, interaction.user)
        if embed is None:
            await interaction.response.send_message(
                embed=error_embed("Invalid Choice", "Pick **rock**, **paper**, or **scissors**."),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(embed=embed)

    @commands.command(name="rps", aliases=["rockpaperscissors"], help="Play Rock Paper Scissors! Usage: !rps rock")
    async def rps_prefix(self, ctx: commands.Context, *, choice: str):
        embed = self._build_rps_embed(choice, ctx.author)
        if embed is None:
            await ctx.reply(
                embed=error_embed("Invalid Choice", "Pick **rock**, **paper**, or **scissors**."),
                mention_author=False,
            )
            return
        await ctx.reply(embed=embed, mention_author=False)

    # ═════════════════════════════════════════════════════════════════════════
    #  5. TRIVIA
    # ═════════════════════════════════════════════════════════════════════════

    def _build_trivia_embed(self, q: dict) -> discord.Embed:
        options_text = "\n".join(
            f"**{TriviaView.LABELS[i]}.** {opt}" for i, opt in enumerate(q["options"])
        )
        embed = base_embed(
            title=f"{q['category']} Trivia",
            description=f"**{q['q']}**\n\n{options_text}",
            color=TRIVIA_COLOR,
        )
        embed.set_footer(text="You have 15 seconds to answer! ⏱️")
        return embed

    @app_commands.command(name="trivia", description="Answer a random trivia question!")
    async def trivia_slash(self, interaction: discord.Interaction):
        q = random.choice(TRIVIA_QUESTIONS)
        view = TriviaView(q, self.trivia_scores)
        embed = self._build_trivia_embed(q)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @commands.command(name="trivia", aliases=["quiz"], help="Answer a random trivia question with interactive buttons!")
    async def trivia_prefix(self, ctx: commands.Context):
        q = random.choice(TRIVIA_QUESTIONS)
        view = TriviaView(q, self.trivia_scores)
        embed = self._build_trivia_embed(q)
        msg = await ctx.reply(embed=embed, view=view, mention_author=False)
        view.message = msg

    # ═════════════════════════════════════════════════════════════════════════
    #  6. FACT
    # ═════════════════════════════════════════════════════════════════════════

    @app_commands.command(name="fact", description="Get a random fun fact!")
    async def fact_slash(self, interaction: discord.Interaction):
        embed = base_embed(
            title="🧠 Fun Fact",
            description=random.choice(FUN_FACTS),
            color=FACT_COLOR,
            user=interaction.user,
        )
        await interaction.response.send_message(embed=embed)

    @commands.command(name="fact", aliases=["funfact", "randomfact"], help="Get a random fun fact!")
    async def fact_prefix(self, ctx: commands.Context):
        embed = base_embed(
            title="🧠 Fun Fact",
            description=random.choice(FUN_FACTS),
            color=FACT_COLOR,
            user=ctx.author,
        )
        await ctx.reply(embed=embed, mention_author=False)

    # ═════════════════════════════════════════════════════════════════════════
    #  7. JOKE
    # ═════════════════════════════════════════════════════════════════════════

    @app_commands.command(name="joke", description="Hear a random joke!")
    async def joke_slash(self, interaction: discord.Interaction):
        joke = random.choice(JOKES)
        use_button = random.random() < 0.5  # 50% chance of a punchline button
        embed = base_embed(
            title="😂 Random Joke",
            description=joke["setup"],
            color=JOKE_COLOR,
            user=interaction.user,
        )
        if use_button:
            view = PunchlineButton(joke["punchline"])
            embed.set_footer(text="Click the button to reveal the punchline! 👇")
            await interaction.response.send_message(embed=embed, view=view)
        else:
            embed.add_field(name="🥁 Punchline", value=joke["punchline"], inline=False)
            await interaction.response.send_message(embed=embed)

    @commands.command(name="joke", aliases=["j", "funny"], help="Hear a random joke!")
    async def joke_prefix(self, ctx: commands.Context):
        joke = random.choice(JOKES)
        use_button = random.random() < 0.5
        embed = base_embed(
            title="😂 Random Joke",
            description=joke["setup"],
            color=JOKE_COLOR,
            user=ctx.author,
        )
        if use_button:
            view = PunchlineButton(joke["punchline"])
            embed.set_footer(text="Click the button to reveal the punchline! 👇")
            await ctx.reply(embed=embed, view=view, mention_author=False)
        else:
            embed.add_field(name="🥁 Punchline", value=joke["punchline"], inline=False)
            await ctx.reply(embed=embed, mention_author=False)

    # ═════════════════════════════════════════════════════════════════════════
    #  8. RATE
    # ═════════════════════════════════════════════════════════════════════════

    def _build_rate_embed(self, thing: str, user: discord.User) -> discord.Embed:
        # Deterministic-ish rating from the thing's text
        score = int(hashlib.md5(thing.lower().encode()).hexdigest(), 16) % 11
        bar = self._progress_bar(score * 10)
        comment = RATE_COMMENTS[score]
        embed = base_embed(
            title="⭐ Rate-O-Matic",
            color=RATE_COLOR,
            user=user,
        )
        embed.add_field(name="📝 Thing", value=thing[:1024], inline=False)
        embed.add_field(name="📊 Rating", value=f"**{score}/10** {bar}", inline=False)
        embed.add_field(name="💬 Verdict", value=comment, inline=False)
        return embed

    @app_commands.command(name="rate", description="Rate anything out of 10!")
    @app_commands.describe(thing="The thing to rate")
    async def rate_slash(self, interaction: discord.Interaction, thing: str):
        await interaction.response.send_message(embed=self._build_rate_embed(thing, interaction.user))

    @commands.command(name="rate", help="Rate anything out of 10! Usage: !rate pineapple pizza")
    async def rate_prefix(self, ctx: commands.Context, *, thing: str):
        await ctx.reply(embed=self._build_rate_embed(thing, ctx.author), mention_author=False)

    # ═════════════════════════════════════════════════════════════════════════
    #  9. SHIP
    # ═════════════════════════════════════════════════════════════════════════

    def _build_ship_embed(self, user1: discord.User, user2: discord.User) -> discord.Embed:
        pct = self._ship_percent(user1.id, user2.id)
        bar = self._progress_bar(pct, length=10)
        comment = "💔 Error: love not found."
        for (lo, hi), text in SHIP_COMMENTS.items():
            if lo <= pct < hi:
                comment = text
                break

        # Build a cute ship name
        name1 = user1.display_name[:len(user1.display_name) // 2]
        name2 = user2.display_name[len(user2.display_name) // 2:]
        ship_name = f"{name1}{name2}"

        embed = base_embed(
            title="💘 Love Calculator",
            color=SHIP_COLOR,
        )
        embed.add_field(
            name="💑 Ship",
            value=f"{user1.mention} ❤️ {user2.mention}\n**Ship Name:** *{ship_name}*",
            inline=False,
        )
        embed.add_field(name="💕 Compatibility", value=f"**{pct}%** {bar}", inline=False)
        embed.add_field(name="💬 Verdict", value=comment, inline=False)
        return embed

    @app_commands.command(name="ship", description="Calculate love compatibility between two users!")
    @app_commands.describe(user1="First person", user2="Second person")
    async def ship_slash(self, interaction: discord.Interaction, user1: discord.User, user2: discord.User):
        await interaction.response.send_message(embed=self._build_ship_embed(user1, user2))

    @commands.command(name="ship", aliases=["love", "compatibility"], help="Ship two users! Usage: !ship @user1 @user2")
    async def ship_prefix(self, ctx: commands.Context, user1: discord.User, user2: discord.User):
        await ctx.reply(embed=self._build_ship_embed(user1, user2), mention_author=False)

    # ═════════════════════════════════════════════════════════════════════════
    #  10. ROAST
    # ═════════════════════════════════════════════════════════════════════════

    @app_commands.command(name="roast", description="Lightheartedly roast someone! 🔥")
    @app_commands.describe(user="Who to roast")
    async def roast_slash(self, interaction: discord.Interaction, user: discord.User):
        roast = random.choice(ROASTS)
        embed = base_embed(
            title="🔥 Roast!",
            description=f"{user.mention}, {roast}",
            color=ROAST_COLOR,
            user=interaction.user,
        )
        await interaction.response.send_message(embed=embed)

    @commands.command(name="roast", help="Lightheartedly roast someone! Usage: !roast @user")
    async def roast_prefix(self, ctx: commands.Context, user: discord.User):
        roast = random.choice(ROASTS)
        embed = base_embed(
            title="🔥 Roast!",
            description=f"{user.mention}, {roast}",
            color=ROAST_COLOR,
            user=ctx.author,
        )
        await ctx.reply(embed=embed, mention_author=False)

    # ═════════════════════════════════════════════════════════════════════════
    #  11. COMPLIMENT
    # ═════════════════════════════════════════════════════════════════════════

    @app_commands.command(name="compliment", description="Send someone a genuine compliment! 💖")
    @app_commands.describe(user="Who to compliment")
    async def compliment_slash(self, interaction: discord.Interaction, user: discord.User):
        comp = random.choice(COMPLIMENTS)
        embed = base_embed(
            title="💖 Compliment",
            description=f"{user.mention}, {comp}",
            color=COMPLIMENT_COLOR,
            user=interaction.user,
        )
        await interaction.response.send_message(embed=embed)

    @commands.command(name="compliment", aliases=["comp"], help="Send someone a genuine compliment! Usage: !compliment @user")
    async def compliment_prefix(self, ctx: commands.Context, user: discord.User):
        comp = random.choice(COMPLIMENTS)
        embed = base_embed(
            title="💖 Compliment",
            description=f"{user.mention}, {comp}",
            color=COMPLIMENT_COLOR,
            user=ctx.author,
        )
        await ctx.reply(embed=embed, mention_author=False)

    # ═════════════════════════════════════════════════════════════════════════
    #  12. MEME
    # ═════════════════════════════════════════════════════════════════════════

    @app_commands.command(name="meme", description="Get a random meme template!")
    async def meme_slash(self, interaction: discord.Interaction):
        meme = random.choice(MEME_TEMPLATES)
        embed = base_embed(
            title=f"😂 {meme['title']}",
            description=meme["desc"],
            color=MEME_COLOR,
            user=interaction.user,
        )
        await interaction.response.send_message(embed=embed)

    @commands.command(name="meme", help="Get a random meme template!")
    async def meme_prefix(self, ctx: commands.Context):
        meme = random.choice(MEME_TEMPLATES)
        embed = base_embed(
            title=f"😂 {meme['title']}",
            description=meme["desc"],
            color=MEME_COLOR,
            user=ctx.author,
        )
        await ctx.reply(embed=embed, mention_author=False)

    # ═════════════════════════════════════════════════════════════════════════
    #  13. ASCII
    # ═════════════════════════════════════════════════════════════════════════

    @app_commands.command(name="ascii", description="Convert text to ASCII block art!")
    @app_commands.describe(text="Text to convert (max 10 characters)")
    async def ascii_slash(self, interaction: discord.Interaction, text: str):
        art = self._text_to_ascii(text)
        embed = base_embed(
            title="🔤 ASCII Art",
            description=f"```\n{art}\n```",
            color=ASCII_COLOR,
            user=interaction.user,
        )
        await interaction.response.send_message(embed=embed)

    @commands.command(name="ascii", help="Convert text to ASCII block art! Usage: !ascii HELLO")
    async def ascii_prefix(self, ctx: commands.Context, *, text: str):
        art = self._text_to_ascii(text)
        embed = base_embed(
            title="🔤 ASCII Art",
            description=f"```\n{art}\n```",
            color=ASCII_COLOR,
            user=ctx.author,
        )
        await ctx.reply(embed=embed, mention_author=False)

    # ═════════════════════════════════════════════════════════════════════════
    #  14. REVERSE
    # ═════════════════════════════════════════════════════════════════════════

    @app_commands.command(name="reverse", description="Reverse any text! 🪞")
    @app_commands.describe(text="Text to reverse")
    async def reverse_slash(self, interaction: discord.Interaction, text: str):
        reversed_text = text[::-1]
        embed = base_embed(
            title="🪞 Reverse Text",
            color=TEXT_FUN_COLOR,
            user=interaction.user,
        )
        embed.add_field(name="📝 Original", value=text[:1024], inline=False)
        embed.add_field(name="🔄 Reversed", value=reversed_text[:1024], inline=False)
        await interaction.response.send_message(embed=embed)

    @commands.command(name="reverse", aliases=["rev", "mirror"], help="Reverse any text!")
    async def reverse_prefix(self, ctx: commands.Context, *, text: str):
        reversed_text = text[::-1]
        embed = base_embed(
            title="🪞 Reverse Text",
            color=TEXT_FUN_COLOR,
            user=ctx.author,
        )
        embed.add_field(name="📝 Original", value=text[:1024], inline=False)
        embed.add_field(name="🔄 Reversed", value=reversed_text[:1024], inline=False)
        await ctx.reply(embed=embed, mention_author=False)

    # ═════════════════════════════════════════════════════════════════════════
    #  15. MOCK
    # ═════════════════════════════════════════════════════════════════════════

    @app_commands.command(name="mock", description="SpOnGeBoB mOcKiNg TeXt!")
    @app_commands.describe(text="Text to mock")
    async def mock_slash(self, interaction: discord.Interaction, text: str):
        mocked = self._mock_text(text)
        embed = base_embed(
            title="🧽 Mocking SpongeBob",
            description=mocked[:4096],
            color=TEXT_FUN_COLOR,
            user=interaction.user,
        )
        await interaction.response.send_message(embed=embed)

    @commands.command(name="mock", aliases=["spongebob", "mocktext"], help="SpOnGeBoB mOcKiNg TeXt!")
    async def mock_prefix(self, ctx: commands.Context, *, text: str):
        mocked = self._mock_text(text)
        embed = base_embed(
            title="🧽 Mocking SpongeBob",
            description=mocked[:4096],
            color=TEXT_FUN_COLOR,
            user=ctx.author,
        )
        await ctx.reply(embed=embed, mention_author=False)


# ═════════════════════════════════════════════════════════════════════════════
#  Setup
# ═════════════════════════════════════════════════════════════════════════════

async def setup(bot):
    await bot.add_cog(Fun(bot))
