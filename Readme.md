<a href="https://cloud.docker.com/repository/docker/voegtlel/auth-manager-mailu-man/builds">
  <img src="https://img.shields.io/docker/cloud/build/voegtlel/auth-manager-mailu-man.svg" alt="Docker build status" />
</a>
<img src="https://img.shields.io/github/license/voegtlel/auth-manager-mailu-man.svg" alt="License" />

# Mailing List Add-On

A mailing list manager working with the alternative backend for mail.

## Docker compose

```
version: '3'
services:
  imap:
    ...

  smtp:
    environment:
      LMTP_ADDRESS: mailu-man

  admin:
    volumes:
      ./mail:/mail

  mailu-man:
    image: voegtlel/auth-manager-mailu-man
    restart: unless-stopped
    volumes:
      ./mail:/mail
    environment:
      MAIL_STORAGE: '/mail'
      
      DOVECOT_ADDRESS: imap:2525
      POSTFIX_ADDRESS: smtp
      
      FRONTEND_BASE_URL: https://manager.example.com
  
```

# License

MIT
