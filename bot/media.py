from __future__ import annotations

from neonize.aioze.client import NewAClient
from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import ContextInfo, Message
from neonize.utils.enum import MediaType
from neonize.utils.message import get_message_type

STICKERABLE_FIELDS = {
    "imageMessage",
    "videoMessage",
    "stickerMessage",
}


def find_sticker_source(message: Message) -> Message | None:
    if is_stickerable(message):
        return message

    quoted = quoted_message(message)
    if quoted and is_stickerable(quoted):
        return quoted

    return None


def quoted_message(message: Message) -> Message | None:
    context = context_info(message)
    if not context or not context.quotedMessage.ByteSize():
        return None
    return context.quotedMessage


def context_info(message: Message) -> ContextInfo | None:
    for _, value in message.ListFields():
        context = getattr(value, "contextInfo", None)
        if context and context.ByteSize():
            return context
    return None


def is_stickerable(message: Message) -> bool:
    for field, value in message.ListFields():
        if field.name in STICKERABLE_FIELDS and _has_download_info(value):
            return True
        if field.name == "documentMessage" and _document_is_stickerable(value):
            return True
    return False


def _document_is_stickerable(document) -> bool:
    mimetype = getattr(document, "mimetype", "") or ""
    return mimetype.startswith(("image/", "video/")) and _has_download_info(document)


def _has_download_info(media) -> bool:
    return bool(
        getattr(media, "directPath", "")
        and getattr(media, "mediaKey", b"")
        and getattr(media, "fileSHA256", b"")
        and getattr(media, "fileEncSHA256", b"")
    )


async def download_media(client: NewAClient, message: Message) -> bytes:
    media = get_message_type(message)
    media_type = MediaType.from_message(message)
    return await client.download_media_with_path(
        media.directPath,
        media.fileEncSHA256,
        media.fileSHA256,
        media.mediaKey,
        media.fileLength,
        media_type,
        media_type.to_mms(),
    )
