import logging, logging.handlers

from logging.handlers import SMTPHandler


class SMTP_SSLHandler(SMTPHandler):
    """
    Implements SSL based SMTP email sending.
    Kudos to: user193661
    """
    def __init__(self, mailhost, fromaddr, toaddrs, subject, credentials=None, secure=None):
        super(SMTP_SSLHandler, self).__init__(mailhost, fromaddr, toaddrs, subject, credentials, secure)


    def emit(self, record):
        """
        Overwrite the logging.handlers.SMTPHandler.emit function with SMTP_SSL.
        Emit a record.
        Format the record and send it to the specified addressees.
        """
        try:
            import smtplib
            from email.utils import formatdate
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            smtp = smtplib.SMTP_SSL(self.mailhost, port, timeout=5)
            msg = self.format(record)
            msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\n\r\n%s" % (self.fromaddr, ", ".join(self.toaddrs), self.getSubject(record), formatdate(), msg)
            if self.username:
                smtp.ehlo()
                smtp.login(self.username, self.password)
            smtp.sendmail(self.fromaddr, self.toaddrs, msg)
            smtp.quit()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)