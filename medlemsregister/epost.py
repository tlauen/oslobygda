"""Felles SMTP-transport. Tvetydig leveringsutfall må kontrollerast før nytt forsøk."""
import os
import smtplib
import ssl


class DeliveryUncertain(RuntimeError):
    pass


def send_message(message):
    port = int(os.environ.get("SMTP_PORT", "587"))
    context = ssl.create_default_context()
    if port == 465:
        smtp = smtplib.SMTP_SSL(
            os.environ["SMTP_HOST"], port, context=context, timeout=15
        )
    else:
        smtp = smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=15)
    accepted = False
    try:
        if port != 465:
            smtp.starttls(context=context)
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        try:
            smtp.send_message(message)
            accepted = True
        except smtplib.SMTPResponseException:
            # Ein eksplisitt SMTP-feil betyr at tenaren avviste sendinga.
            raise
        except smtplib.SMTPRecipientsRefused:
            raise
        except Exception:
            # Tenaren kan ha teke imot meldinga før sambandet forsvann.
            raise DeliveryUncertain("Uvisst om SMTP-tenaren tok imot meldinga.") from None

    finally:
        try:
            smtp.quit()
        except Exception:
            smtp.close()
            if not accepted:
                pass
