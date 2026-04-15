import logging
from typing import Optional
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class AliyunNotificationService:
    """Alibaba Cloud SMS and Email service"""

    @staticmethod
    def send_sms(phone: str, code: str) -> bool:
        """Send SMS verification code"""
        if not settings.alibaba_access_key_id or not settings.alibaba_access_key_secret:
            logger.warning("[AliyunNotification] SMS not configured, skipping")
            return False

        try:
            from alibabacloud_dysmsapi20170525.client import Client
            from alibabacloud_dysmsapi20170525.models import SendSmsRequest
            from alibabacloud_tea_openapi import models as open_api_models

            config = open_api_models.Config(
                access_key_id=settings.alibaba_access_key_id,
                access_key_secret=settings.alibaba_access_key_secret,
                endpoint="dysmsapi.aliyuncs.com",
            )
            client = Client(config)

            request = SendSmsRequest(
                phone_numbers=phone,
                sign_name=settings.alibaba_sms_sign_name,
                template_code=settings.alibaba_sms_template_code,
                template_param=f'{{"code":"{code}"}}',
            )

            response = client.send_sms(request)
            logger.info(f"[AliyunNotification] SMS sent to {phone}: {response.body}")
            return True
        except Exception as e:
            logger.error(f"[AliyunNotification] SMS failed: {e}")
            return False

    @staticmethod
    def send_email(email: str, code: str) -> bool:
        """Send email verification code"""
        if not settings.alibaba_access_key_id or not settings.alibaba_access_key_secret:
            logger.warning("[AliyunNotification] Email not configured, skipping")
            return False

        try:
            from alibabacloud_dm.models import SingleSendMailRequest
            from alibabacloud_tea_openapi import models as open_api_models
            from alibabacloud_dm.client import Client as DMClient

            config = open_api_models.Config(
                access_key_id=settings.alibaba_access_key_id,
                access_key_secret=settings.alibaba_access_key_secret,
                endpoint="dm.aliyuncs.com",
            )
            client = DMClient(config)

            request = SingleSendMailRequest(
                account_name=settings.alibaba_email_account,
                address_from=settings.alibaba_email_account,
                address_to=email,
                subject="您的验证码",
                html_body=f"您的验证码是：{code}，10分钟内有效。",
            )

            response = client.single_send_mail(request)
            logger.info(f"[AliyunNotification] Email sent to {email}: {response.body}")
            return True
        except Exception as e:
            logger.error(f"[AliyunNotification] Email failed: {e}")
            return False


aliyun_notification = AliyunNotificationService()
