from __future__ import print_function


class EmailService(object):

    def send_email(self, subject, sender, recipients, body):
        print(subject, sender, recipients, body)
