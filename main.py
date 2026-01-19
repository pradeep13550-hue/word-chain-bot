import re
import asyncio
import random
from telethon import TelegramClient, events
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import (
    SendMessageTypingAction,
    MessageEntityItalic,
    MessageEntityMentionName
)
from loguru import logger

# ================= CONFIG =================

API_ID = 9285198
API_HASH = "33e4caa483022ef6b23d3a7ead6cb88b"
SESSION = "session/wordchain"
WORDCHAIN_BOT = "on9wordchainbot"
WORDS_FILE = "words.txt"

# ================= REGEX =================

RESPONSE_PATTERN = re.compile(r"(is accepted\.|has been used\.|is not)")
WORD_INFO_PATTERN = re.compile(r"Your word must start with (.+)")
WORD_LENGTH_PATTERN = re.compile(r"\d+")


class WordChainBot:

    def __init__(self):
        self.client = TelegramClient(SESSION, API_ID, API_HASH)
        self.used_words = {}
        self.active_turns = set()

        # ==================================================
        # TELETHON COMPATIBILITY LAYER (DO NOT REMOVE)
        # Implements wait_for_event without wait_for
        # ==================================================
        async def _wait_for_event(self, event_builder, timeout=None):
            loop = asyncio.get_running_loop()
            future = loop.create_future()

            async def handler(event):
                if not future.done():
                    future.set_result(event)

            self.add_event_handler(handler, event_builder)

            try:
                return await asyncio.wait_for(future, timeout)
            finally:
                self.remove_event_handler(handler, event_builder)

        TelegramClient.wait_for_event = _wait_for_event
        # ==================================================

        self.client.add_event_handler(
            self.listener,
            events.NewMessage(from_users=WORDCHAIN_BOT)
        )

    # ================= HELPERS =================

    def find_words(self, start, length, include=None):
        results = []
        with open(WORDS_FILE, "r", encoding="utf-8") as f:
            for word in f:
                word = word.strip().lower()
                if len(word) != length:
                    continue
                if not word.startswith(start.lower()):
                    continue
                if include and include.lower() not in word:
                    continue
                results.append(word)
        random.shuffle(results)
        return results

    async def extract_mention(self, event, text):
        try:
            turn_index = text.index("Turn:")
            for ent in event.message.entities or []:
                if isinstance(ent, MessageEntityMentionName):
                    if ent.offset > turn_index:
                        return ent.user_id
        except Exception:
            pass
        return None

    def extract_requirements(self, text):
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
        if len(caps) == 2:
            return caps[0], length, caps[1]
        return None

    async def wait_response(self, chat_id, word, timeout=4):
        try:
            event = await self.client.wait_for_event(
                events.NewMessage(
                    chats=chat_id,
                    from_users=WORDCHAIN_BOT,
                    pattern=RESPONSE_PATTERN
                ),
                timeout=timeout
            )

            text = event.text.lower()

            for ent in event.message.entities or []:
                if isinstance(ent, MessageEntityItalic):
                    italic = event.text[ent.offset:ent.offset + ent.length]
                    if word.lower() in italic.lower():
                        if "accepted" in text:
                            return "accepted"
                        if "used" in text or "is not" in text:
                            return "rejected"

            return "unknown"

        except asyncio.TimeoutError:
            return "timeout"
        except Exception as e:
            logger.error(f"[WAIT] {e}")
            return "error"

    async def submit_word(self, chat_id, word):
        await asyncio.sleep(2)
        await self.client(SetTypingRequest(
            peer=chat_id,
            action=SendMessageTypingAction()
        ))
        await self.client.send_message(chat_id, word)

    # ================= MAIN LISTENER =================

    async def listener(self, event):
        text = event.text or ""
        chat_id = event.chat_id

        if not event.is_group or "Turn:" not in text:
            return

        if chat_id in self.active_turns:
            return

        me = await self.client.get_me()
        mention_id = await self.extract_mention(event, text)

        if mention_id != me.id:
            return

        req = self.extract_requirements(text)
        if not req:
            return

        start, length, include = req
        words = self.find_words(start, length, include)

        if not words:
            return

        self.active_turns.add(chat_id)

        try:
            for word in words:
                await self.submit_word(chat_id, word)
                status = await self.wait_response(chat_id, word)

                # ✅ Accepted → stop immediately
                if status == "accepted":
                    break

                # ❌ Rejected → try next word
                if status == "rejected":
                    continue

                # ⏱ timeout / unknown / error → stop
                break

        finally:
            self.active_turns.discard(chat_id)


# ================= START =================

if __name__ == "__main__":
    logger.info("Starting WordChain Userbot")

    bot = WordChainBot()
    bot.client.start()
    bot.client.run_until_disconnected()
