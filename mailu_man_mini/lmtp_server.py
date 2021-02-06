import asyncio
import email
import logging
import os
import signal
from typing import List, Optional, Awaitable

import aiofiles
import httpx
import time
from email.message import Message
from email.utils import parseaddr


from aiosmtpd.controller import Controller
from aiosmtpd.handlers import CRLF
from aiosmtpd.lmtp import LMTP
from aiosmtpd.smtp import Session, Envelope

from pydantic import BaseModel

from mailu_man_mini.config import config
from mailu_man_mini.mailer import mailer_postfix, mailer_dovecot
from mailu_man_mini.token_gen import generate_token


OK_250 = '250 Ok'
ERR_451 = '451 Requested action aborted: error in processing'
ERR_501 = '501 Message has defects'
# ERR_502 = '502 Error: command HELO not implemented'
ERR_550 = '550 Requested action not taken: mailbox unavailable'


logger = logging.getLogger(__name__)


httpx_client: httpx.AsyncClient


async def startup():
    global openid_mail_endpoint, httpx_client

    httpx_client = httpx.AsyncClient(auth=(config.mailu_oauth_client_id, config.mailu_oauth_client_secret))

    # Verify that the authentication server is available
    response = await httpx_client.get(f"{config.mailu_oauth_url}/.well-known/openid-configuration")
    response.raise_for_status()

    openid_mail_endpoint = f"{config.mailu_oauth_url}/mail"


async def shutdown():
    global openid_mail_endpoint, httpx_client
    await httpx_client.aclose()
    del openid_mail_endpoint
    del httpx_client


class EmailListMapping(BaseModel):
    email: str
    is_mailing_list: bool
    has_postbox: Optional[bool]
    notify_sender: Optional[bool]
    send_original_to_notifiers: Optional[bool]
    notify_addresses: Optional[List[str]]


async def get_mailing_list_types(emails: List[str]) -> List[EmailListMapping]:
    response = await httpx_client.get(f"/mail/list/forward/{','.join(emails)}")
    if response.status_code == 200:
        return [EmailListMapping.validate(mapping) for mapping in response.json()]
    return []


async def get_mailing_list_targets(email: str) -> List[str]:
    response = await httpx_client.get(f"/mail/list/send/{email}")
    if response.status_code == 200:
        return [target_mail for target_mail in response.json()]
    return []


async def save_mail(from_address: str, id: str, path: str, mailing_list_address: str):
    response = await httpx_client.post(f"/mail/list/save/{mailing_list_address}", json={
        'id': id,
        'path': path,
        'from_address': from_address,
    })
    if response.status_code != 200:
        response.raise_for_status()


message_queue: asyncio.Queue = asyncio.Queue()


class LMTPHandler:
    async def handle_DATA(self, server: LMTP, session: Session, envelope: Envelope):
        try:
            msg: Message = email.message_from_bytes(envelope.content)
        except Exception:
            logger.exception('LMTP message parsing')
            return CRLF.join(ERR_451 for _to in envelope.rcpt_tos)
        if msg.defects:
            return ERR_501

        from_name, from_address = parseaddr(envelope.mail_from)[1].lower()
        if '@' not in from_address:
            return CRLF.join(ERR_550 for _to in envelope.rcpt_tos)

        # RFC 2033 requires a status code for every recipient
        status = []
        target_addresses = []
        for to in envelope.rcpt_tos:
            to = parseaddr(to)[1].lower()
            if '@' not in to:
                status.append(ERR_550)
            target_addresses.append(to)
            status.append(OK_250)

        targets = await get_mailing_list_types(target_addresses)

        senders: List[Awaitable] = []
        if any(target.is_mailing_list for target in targets):
            msg_id = generate_token(48)
            stored_message_path = os.path.join(config.mail_storage, f'{msg_id}.eml')
            async with aiofiles.open(stored_message_path, 'wb') as wf:
                await wf.write(envelope.content)
        else:
            msg_id = ''
            stored_message_path = ''
        for target in targets:
            if target.is_mailing_list:
                if target.notify_addresses:
                    senders.append(
                        mailer_postfix.async_send_mail(
                            config.default_language,
                            'notify_notifier',
                            envelope.mail_from,
                            target.notify_addresses,
                            {
                                'from': from_address, 'from_name': from_name, 'config': config, 'msg_id': msg_id
                            }
                        )
                    )
                if target.send_original_to_notifiers:
                    senders.append(
                        mailer_postfix.async_send_mail_raw(
                            envelope.mail_from, target.notify_addresses, envelope.content
                        )
                    )
                if target.notify_sender:
                    senders.append(mailer_postfix.async_send_mail(
                        config.default_language,
                        'notify_sender',
                        target.email,
                        [from_address],
                        {
                            'from': from_address, 'from_name': from_name, 'config': config
                        }
                    ))
                senders.append(save_mail(envelope.mail_from, msg_id, stored_message_path, target.email))
        senders.append(
            mailer_dovecot.async_send_mail_raw(
                envelope.mail_from,
                [target.email for target in targets if not target.is_mailing_list or target.has_postbox],
                envelope.content,
            )
        )

        for result in await asyncio.gather(senders, return_exceptions=True):
            if isinstance(result, BaseException):
                logger.exception(str(result), exc_info=result)

        return CRLF.join(status)


class LMTPController(Controller):
    def factory(self):
        server = LMTP(self.handler, enable_SMTPUTF8=True, decode_data=False)
        server.__ident__ = 'MailU-Man Mini 0.0.1'
        return server


def _main():
    lmtp = LMTPController(LMTPHandler(), hostname=config.hostname, port=config.port)
    lmtp.start()
    running = True

    def sigint(signal, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, sigint)
    try:
        logger.info(f"LTMP running at {config.port}")
        while running:
            time.sleep(1)
    finally:
        lmtp.stop()


if __name__ == '__main__':
    _main()
