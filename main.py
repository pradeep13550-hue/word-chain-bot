import asyncio
import random
import re
import logging

from pyrogram import Client, filters, enums
from pyrogram.types import Message

# ================= CONFIG =================

API_ID = 123456        # <-- PUT YOUR API ID
API_HASH = "API_HASH"  # <-- PUT YOUR API HASH

# =========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

used_words = {}

RESPONSE_PATTERN = re.compile(r"(is accepted\.|has been used\.|is not)")
WORD_INFO_PATTERN = re.compile(r"Your word must start with (.+)")
WORD_LENGTH_PATTERN = re.compile(r"\d+")


def is_game_enabled():
    def decorator(func):
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def find_random_words(file_path, start_letter, word_length, include_letter=None):
    results = []
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            word = line.strip().upper()
            if len(word) != word_length:
                continue
            if not word.startswith(start_letter):
                continue
            if include_letter and include_letter not in word:
                continue
            results.append(word)
    return results


@Client.on_message(filters.user("on9wordchainbot") & filters.group)
@is_game_enabled()
async def wordchain_listener(client, message: Message):
    logger.debug(f"[MAIN] Received message: {message.text}")

    try:
        text = message.text
        chat_id = message.chat.id

        if "Turn:" not in text:
            return

        first_mention = await extract_first_mention(message, text)
        if not first_mention or first_mention.id != client.me.id:
            return

        word_requirements = await extract_word_requirements(text)
        if not word_requirements:
            return

        start_letter, word_length, include_letter = word_requirements

        filtered_words = find_random_words(
            "words.txt", start_letter, word_length, include_letter
        )

        if not filtered_words:
            await client.send_message(client.me.id, "No suitable word found.")
            return

        if chat_id not in used_words:
            used_words[chat_id] = []

        success = await attempt_word_submission(
            client, chat_id, filtered_words, used_words[chat_id]
        )

        if success:
            logger.info("Word successfully submitted")

    except Exception as e:
        logger.error(f"Main handler error: {e}")
        await client.send_message(client.me.id, f"ERROR: {e}")


async def extract_first_mention(message: Message, text: str):
    entities = message.entities or []
    if not entities:
        return None

    turn_index = text.index("Turn:")

    for entity in entities:
        if (
            entity.type == enums.MessageEntityType.TEXT_MENTION
            and entity.offset > turn_index
        ):
            return entity.user
    return None


async def extract_word_requirements(text: str):
    match = WORD_INFO_PATTERN.search(text)
    if not match:
        return None

    info = match.group(1)
    capitals = re.findall(r"[A-Z]", info)
    length_match = WORD_LENGTH_PATTERN.search(info)

    if not length_match:
        return None

    word_length = int(length_match.group())

    if len(capitals) == 1:
        return capitals[0], word_length, None
    elif len(capitals) == 2:
        return capitals[0], word_length, capitals[1]

    return None


async def attempt_word_submission(
    client, chat_id, filtered_words, used_words_list, max_attempts=5
):
    for _ in range(max_attempts):
        selected_word = await select_unused_word(
            filtered_words, used_words_list
        )
        if not selected_word:
            continue

        try:
            await asyncio.sleep(4)
            await client.send_chat_action(chat_id, enums.ChatAction.TYPING)
            await client.send_message(chat_id, selected_word)
            used_words_list.append(selected_word)
        except Exception:
            continue

        result = await wait_for_response(client, chat_id, selected_word)

        if result == "accepted":
            return True
        elif result == "format_error":
            return False

    return False


async def select_unused_word(filtered_words, used_words_list, max_tries=10):
    for _ in range(max_tries):
        word = random.choice(filtered_words)
        if word not in used_words_list:
            return word
    return None


async def wait_for_response(client, chat_id, submitted_word, timeout=4):
    try:
        response = await client.listen.Message(
            filters.regex(RESPONSE_PATTERN)
            & filters.user("on9wordchainbot")
            & filters.chat(chat_id),
            timeout=timeout,
        )

        text = response.text.lower()

        if "does not start" in text or "does not include" in text:
            return "format_error"

        for entity in response.entities or []:
            if entity.type == enums.MessageEntityType.ITALIC:
                italic_text = response.text[
                    entity.offset : entity.offset + entity.length
                ]
                if submitted_word.lower() in italic_text.lower():
                    if "accepted" in text:
                        return "accepted"
                    return "rejected"

        return "unclear"

    except asyncio.TimeoutError:
        return "timeout"
    except Exception:
        return "error"


app = Client(
    "wordchain",
    api_id=API_ID,
    api_hash=API_HASH,
    workdir="session"
)

app.run()
