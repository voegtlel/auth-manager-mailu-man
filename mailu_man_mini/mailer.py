import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import aiosmtplib
from typing import Tuple, List

from mako.lookup import TemplateLookup

from mailu_man_mini.config import config


class Mailer:
    def __init__(self, target_address: str):
        self.target_address = target_address
        self.template_lookup = TemplateLookup(
            directories=[os.path.join(os.path.dirname(__file__), 'mail_templates')],
            strict_undefined=True,
        )

    def connect(self) -> smtplib.SMTP:
        return smtplib.SMTP(self.target_address, 25)

    def async_mailer(self) -> aiosmtplib.SMTP:
        return aiosmtplib.SMTP(self.target_address, 25)

    def _render_template(self, language: str, name: str, **kwargs) -> Tuple[str, str]:
        if language != 'en_us' and not self.template_lookup.has_template(f'{language}/{name}'):
            language = 'en_us'

        template = self.template_lookup.get_template(f'{language}/{name}')
        data = template.render(
            config=config,
            **kwargs,
        )
        return data.split('\n', 1)

    async def async_send_mail(self, language: str, name: str, from_addr: str, to: List[str], context: dict):
        html_title, html_data = self._render_template(language, name + '.html', **context)
        txt_title, txt_data = self._render_template(language, name + '.txt', **context)
        assert txt_title == html_title

        message = MIMEMultipart('alternative')
        message['Subject'] = txt_title
        message.attach(MIMEText(html_data, 'html'))
        message.attach(MIMEText(txt_data, 'plain'))

        async with self.async_mailer() as connected_mailer:
            await connected_mailer.sendmail(from_addr, to, message.as_bytes())

    async def async_send_mail_raw(self, from_addr: str, to: List[str], content: bytes):
        async with self.async_mailer() as connected_mailer:
            await connected_mailer.sendmail(from_addr, to, content)


mailer_postfix = Mailer(config.postfix_address)
mailer_dovecot = Mailer(config.dovecot_address)
