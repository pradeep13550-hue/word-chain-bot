import re
import asyncio
import random
from kurigram import Client
from telethon import events
from telethon.tl.types import MessageEntityItalic, MessageEntityTextMention
from loguru import logger

# ================= CONFIG =================

api_id = 9285198
api_hash = "39QDt7fVWUuPqLsPDAF3XkuDQEKiZkxN9z"

client = Client(
    session="session/wordchain",
    api_id=api_id,
    api_hash=api_hash
)

WORDCHAIN_BOT_USERNAME = "on9wordchainbot"

# ================= REGEX =================

RESPONSE_PATTERN = re.compile(r"(is accepted\.|has been used\.|is not)")
WORD_INFO_PATTERN = re.compile(r"Your word must start with (.+)")
WORD_LENGTH_PATTERN = re.compile(r'\d+')

used_words = {}

# ================= HELPERS =================

def is_game_enabled():
    def decorator(func):
        async def wrapper(event):
            return await func(event)
        return wrapper
    return decorator


def find_random_words(file_path, start_letter, word_length, include_letter=None):
    results = []
    with open(file_path, "r", encoding="utf-8") as f:
        for word in f:
            word = word.strip().lower()
            if len(word) != word_length:
                continue
            if not word.startswith(start_letter.lower()):
                continue
            if include_letter and include_letter.lower() not in word:
                continue
            results.append(word)
    random.shuffle(results)
    return results


async def extract_first_mention(event, text):
    try:
        entities = event.message.entities or []
        turn_index = text.index("Turn:")

        for entity in entities:
            if isinstance(entity, MessageEntityTextMention):
                if entity.offset > turn_index:
                    return entity.user_id
        return None
    except Exception as e:
        logger.error(f"[MENTION] {e}")
        return None


async def extract_word_requirements(text):
    try:
        match = WORD_INFO_PATTERN.search(text)
        if not match:
            return None

        line = match.group(1)
        caps = re.findall(r"[A-Z]", line)
        length_match = WORD_LENGTH_PATTERN.search(line)

        if not length_match:
            return None

        length = int(length_match.group())

        if len(caps) == 1:
            return caps[0], length, None
        elif len(caps) == 2:
            return caps[0], length, caps[1]
        return None
    except Exception as e:
        logger.error(f"[REQ] {e}")
        return None


async def select_unused_word(words, used, max_tries=10):
    for _ in range(max_tries):
        w = random.choice(words)
        if w not in used:
            return w
    return None


async def wait_for_response(chat_id, submitted_word, timeout=4):
    try:
        event = await client.wait_for_event(
            events.NewMessage(
                chats=chat_id,
                from_users=WORDCHAIN_BOT_USERNAME,
                pattern=RESPONSE_PATTERN
            ),
            timeout=timeout
        )

        text = event.text.lower()

        if "does not start with" in text or "does not include" in text:
            return "format_error"

        if not event.message.entities:
            return "no_entities"

        for ent in event.message.entities:
            if isinstance(ent, MessageEntityItalic):
                italic = event.text[ent.offset:ent.offset + ent.length]
                if submitted_word.lower() in italic.lower():
                    if "accepted" in text:
                        return "accepted"
                    if "used" in text or "is not" in text:
                        return "rejected"

        return "unclear"

    except asyncio.TimeoutError:
        return "timeout"
    except Exception as e:
        logger.error(f"[WAIT] {e}")
        return "error"


async def attempt_word_submission(chat_id, words, used, max_attempts=5):
    for _ in range(max_attempts):
        word = await select_unused_word(words, used)
        if not word:
            continue

        await asyncio.sleep(4)
        await client.send_chat_action(chat_id, "typing")
        await client.send_message(chat_id, word)

        used.append(word)

        result = await wait_for_response(chat_id, word)

        if result == "accepted":
            return True
        if result == "format_error":
            return False

    return False

# ================= MAIN LISTENER =================

@client.on(events.NewMessage(from_users=WORDCHAIN_BOT_USERNAME))
@is_game_enabled()
async def wordchain_listener(event):
    try:
        text = event.text
        chat_id = event.chat_id

        if "Turn:" not in text or not event.is_group:
            return

        me = await client.get_me()
        mention_id = await extract_first_mention(event, text)

        if mention_id != me.id:
            return

        req = await extract_word_requirements(text)
        if not req:
            return

        start, length, include = req

        words = find_random_words("words.txt", start, length, include)
        if not words:
            await client.send_message("me", "No suitable word found")
            return

        if chat_id not in used_words:
            used_words[chat_id] = []

        await attempt_word_submission(chat_id, words, used_words[chat_id])

    except Exception as e:
        logger.error(f"[MAIN] {e}")
        await client.send_message("me", f"ERROR: {e}")

# ================= START =================

logger.info("Starting Kurigram WordChain Userbot")
client.run()
