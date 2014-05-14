import unittest
import app as flask_app
from mock import MagicMock


class TestFlaskApp(unittest.TestCase):
    def setUp(self):
        self.lorem = ("Lorem ipsum dolor sit amet, "
                      "consectetur adipiscing elit. "
                      "Cras molestie rhoncus eros ve elementum.\n")
        template = (
            "{}"
            "Line 2"
            "line 3"
            "LINE IV"
            "> I'm inquring about your widgets, how much are they?\n"
            "> Are they expensive widgets?\n"
            "> John Doe")
        self.lorem_with_extra_lines = template.format(self.lorem)

        class MockMessageCreate():
            @property
            def sid(self):
                return "SM00000000000000000000000000000000"

        def sendgrid_send(sendgrid_message):
            return (200, {'message': 'success'})

        flask_app.twilio_api = MagicMock()
        flask_app.twilio_api.messages.create.return_value = MockMessageCreate()
        flask_app.sendgrid_api.send = MagicMock(side_effect=sendgrid_send)
        flask_app.logging = MagicMock()

        settings = {'EMAIL_DOMAIN': 'sms.example.com',
                    'TWILIO_ACCOUNT_SID': True,
                    'TWILIO_AUTH_TOKEN': True,
                    'SENDGRID_USERNAME': True,
                    'SENDGRID_PASSWORD': True}
        flask_app.konf.use_dict(settings)
        flask_app.address_book = {
            '+14155551212': 'alice@example.com',
            '+14155551213': 'bob@example.com',
            '+14155551214': 'eve@example.com'
        }
        self.app = flask_app.app.test_client()

    def tearDown(self):
        pass

    def test_missing_configration_varibles_shows_warning(self):
        settings = {'EMAIL_DOMAIN': 'example.com',
                    'TWILIO_ACCOUNT_SID': False,
                    'TWILIO_AUTH_TOKEN': False,
                    'SENDGRID_USERNAME': False,
                    'SENDGRID_PASSWORD': False}
        flask_app.konf.use_dict(settings)
        rv = self.app.get('/')
        self.assertEquals("500 INTERNAL SERVER ERROR", rv.status)
        self.assertIn("missing", rv.data)

        self.assertNotIn("EMAIL_DOMAIN", rv.data)
        for env_var in ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN',
                        'SENDGRID_USERNAME', 'SENDGRID_PASSWORD']:
            self.assertIn(env_var, rv.data)

        settings = {'EMAIL_DOMAIN': False,
                    'TWILIO_ACCOUNT_SID': True,
                    'TWILIO_AUTH_TOKEN': True,
                    'SENDGRID_USERNAME': True,
                    'SENDGRID_PASSWORD': True}
        flask_app.konf.use_dict(settings)
        rv = self.app.get('/')
        self.assertEquals("500 INTERNAL SERVER ERROR", rv.status)
        self.assertIn("missing", rv.data)
        self.assertIn("EMAIL_DOMAIN", rv.data)
        for env_var in ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN',
                        'SENDGRID_USERNAME', 'SENDGRID_PASSWORD']:
            self.assertNotIn(env_var, rv.data)

    def test_has_default_route(self):
        path = "/"
        rv = self.app.get(path)
        self.assertIn("configured correctly", rv.data)
        self.assertEquals("200 OK", rv.status)

    def test_email_address_to_phone_number(self):
        example_input = '14155551212@sms.example.com'
        result_expected = '+14155551212'
        result_actual = flask_app.email_to_phone(example_input)
        self.assertEquals(result_expected, result_actual)

    def test_phone_number_to_email_address(self):
        example_inputs = ['+14155551212', '(415) 555-1212', '4155551212']
        result_expected = '14155551212@sms.example.com'
        for example_input in example_inputs:
            result_actual = flask_app.phone_to_email(example_input)
            self.assertEquals(result_expected, result_actual)

    def test_sms_with_sendgrid_failure(self):
        def sendgrid_send(msg):
            return (400, {'message': 'error', 'errors': ['Mocked reply']})

        flask_app.sendgrid_api.send = MagicMock(side_effect=sendgrid_send)

        example_input = {
            'To': '+14155551212',
            'From': '+14155551213',
            'Body': self.lorem
        }

        path = "/handle-sms"
        rv = self.app.post(path, data=example_input)

        expected_error = ("Error sending message to SendGrid: Mocked reply")
        flask_app.logging.warning.assert_called_with(expected_error)
        self.assertEquals("400 BAD REQUEST", rv.status)
        self.assertIn("Error sending message to SendGrid", rv.data)
        self.assertIn("Mocked reply", rv.data)

    def test_email_for_phone(self):
        example_inputs = ['+14155551212', '4155551212', '(415) 555-1212']
        result_expected = 'alice@example.com'
        lookup = flask_app.Lookup()
        for example_input in example_inputs:
            result_actual = lookup.email_for_phone(example_input)
            self.assertEquals(result_expected, result_actual)

    def test_sms_triggers_email(self):
        example_input = {
            'To': '+14155551212',
            'From': '+14155551213',
            'Body': self.lorem
        }

        path = "/handle-sms"
        rv = self.app.post(path, data=example_input)

        self.assertIn("<Response></Response>", rv.data)
        self.assertEquals("200 OK", rv.status)

        (args, kwargs) = flask_app.sendgrid_api.send.call_args
        msg = args[0]
        self.assertEquals(msg.to, ['alice@example.com'])
        self.assertEquals(msg.from_email, '14155551213@sms.example.com')
        self.assertEquals(msg.subject, 'Text message')
        self.assertEquals(msg.text, self.lorem)

    def test_sms_from_unknown_number(self):
        example_input = {
            'To': '+14155551219',
            'From': '+14155551213',
            'Body': self.lorem
        }

        path = "/handle-sms"
        rv = self.app.post(path, data=example_input)

        expected_error = ("No email address is configured "
                          "to receive SMS messages sent to '+14155551219'"
                          " - Try updating the 'address-book.cfg' file?")
        flask_app.logging.warning.assert_called_with(expected_error)
        self.assertFalse(flask_app.sendgrid_api.send.called)
        self.assertEquals("400 BAD REQUEST", rv.status)

    def test_email_triggers_sms(self):
        example_input = {
            'to': '14155551213@sms.example.com',
            'envelope': '{"from":"alice@example.com"}',
            'text': self.lorem
        }
        path = "/handle-email"
        rv = self.app.post(path, data=example_input)
        client = flask_app.twilio_api
        self.assertEquals('SM00000000000000000000000000000000', rv.data)
        client.messages.create.assert_called_with(to='+14155551213',
                                                  from_='+14155551212',
                                                  body=self.lorem)
        self.assertEquals("200 OK", rv.status)

    def test_email_with_twilio_failure(self):
        example_input = {
            'to': '14155551213@sms.example.com',
            'envelope': '{"from":"alice@example.com"}',
            'text': self.lorem
        }

        def side_effect():
            from twilio import TwilioRestException
            raise TwilioRestException('Test exception')
        msgs = flask_app.twilio_api.messages
        msgs.create = MagicMock(side_effect=side_effect)

        path = "/handle-email"
        rv = self.app.post(path, data=example_input)
        expected_error = "Error sending message to Twilio"
        flask_app.logging.warning.assert_called_with(expected_error)
        self.assertEquals("400 BAD REQUEST", rv.status)

    def test_email_only_reads_first_line(self):
        example_input = {
            'to': '14155551213@sms.example.com',
            'envelope': '{"from":"alice@example.com"}',
            'text': self.lorem_with_extra_lines
        }
        path = "/handle-email"
        rv = self.app.post(path, data=example_input)
        client = flask_app.twilio_api
        self.assertEquals('SM00000000000000000000000000000000', rv.data)
        client.messages.create.assert_called_with(to='+14155551213',
                                                  from_='+14155551212',
                                                  body=self.lorem)
        self.assertEquals("200 OK", rv.status)

    def test_email_to_invalid_number(self):
        example_input = {
            'to': '42@sms.example.com',
            'envelope': '{"from":"alice@example.com"}',
            'text': self.lorem
        }
        path = "/handle-email"
        rv = self.app.post(path, data=example_input)
        expected_error = ("Invalid phone number in email address: "
                          "42@sms.example.com")
        flask_app.logging.warning.assert_called_with(expected_error)
        client = flask_app.twilio_api
        self.assertFalse(client.messages.create.called)
        # So that SendGrid doesn't keep trying to deliver the email
        self.assertEquals("200 OK", rv.status)

    def test_email_from_unknown_address(self):
        example_input = {
            'to': '14155551212@sms.example.com',
            'envelope': '{"from":"fake@example.com"}',
            'text': self.lorem
        }
        path = "/handle-email"
        rv = self.app.post(path, data=example_input)
        expected_error = ("The email address 'fake@example.com' "
                          "is not configured to send SMS via this application"
                          " - Try updating the 'address-book.cfg' file?")
        client = flask_app.twilio_api
        self.assertFalse(client.messages.create.called)
        # So that SendGrid doesn't keep trying to deliver the email
        self.assertEquals("200 OK", rv.status)
        flask_app.logging.warning.assert_called_with(expected_error)

    def test_check_address_book_dict_for_duplicates(self):
        flask_app.address_book = {
            '+14155551212': 'alice@example.com',
            '+14155551213': 'bob@example.com',
            '+14155551214': 'eve@example.com',
            '+14155551215': 'bob@example.com'
        }

        rv = self.app.get('/')
        self.assertEquals("500 INTERNAL SERVER ERROR", rv.status)
        expected_text = ("Only one email address can be "
                         "configured per phone number.")
        self.assertIn(expected_text, rv.data)
