# -*- coding: utf-8 -*-
"""邮箱验证码发送工具"""
import smtplib
import threading
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import Config


def _send_email_sync(to_email: str, code: str):
    """同步发送验证码邮件（在子线程中调用）"""
    subject = "【Atmos 智能家居】邮箱验证码"
    html = f"""\
<html>
<body style="font-family: 'Segoe UI', Arial, sans-serif; padding: 0; margin: 0; background: #f5f5f5;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background: #f5f5f5; padding: 40px 0;">
    <tr>
      <td align="center">
        <table width="480" cellpadding="0" cellspacing="0" style="background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 16px rgba(0,0,0,0.06);">
          <tr>
            <td style="padding: 40px 48px 32px; text-align: center; border-bottom: 1px solid #eee;">
              <div style="font-size: 22px; font-weight: 600; color: #1a1a1a; letter-spacing: -0.5px;">
                <span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #4caf84; margin-right: 10px; box-shadow: 0 0 8px rgba(76,175,132,0.4);"></span>
                Atmos
              </div>
              <div style="font-size: 13px; color: #999; margin-top: 8px;">智能家居遥测平台</div>
            </td>
          </tr>
          <tr>
            <td style="padding: 36px 48px 40px;">
              <p style="font-size: 15px; color: #333; line-height: 1.7; margin: 0 0 24px;">
                您好，您正在注册 <strong>Atmos 智能家居</strong> 账号。<br>
                请使用以下验证码完成邮箱验证：
              </p>
              <div style="background: #f9fafb; border-radius: 8px; padding: 24px; text-align: center; margin-bottom: 28px;">
                <span style="font-family: 'SF Mono', 'Consolas', monospace; font-size: 36px; font-weight: 700; letter-spacing: 12px; color: #1a1a1a;">{code}</span>
              </div>
              <p style="font-size: 13px; color: #999; line-height: 1.6; margin: 0;">
                验证码 <strong>{Config.CODE_EXPIRE_MINUTES} 分钟</strong> 内有效，请勿泄露给他人。<br>
                如非本人操作，请忽略此邮件。
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding: 20px 48px; background: #f9fafb; text-align: center;">
              <span style="font-size: 12px; color: #bbb;">Atmos Smart Home · v1.0</span>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = Config.SMTP_USER
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL(Config.SMTP_HOST, Config.SMTP_PORT) as server:
        server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        server.sendmail(msg["From"], [to_email], msg.as_string())


# 简单的内存频率限制 {email: last_send_timestamp}
_rate_limit_store: dict[str, float] = {}


def check_rate_limit(email: str) -> int | None:
    """检查发送频率限制，返回剩余等待秒数；若未受限返回 None"""
    now = time.time()
    last = _rate_limit_store.get(email)
    if last is not None:
        elapsed = now - last
        if elapsed < Config.CODE_RATE_LIMIT_SECONDS:
            return int(Config.CODE_RATE_LIMIT_SECONDS - elapsed)
    return None


def send_code_email(to_email: str, code: str):
    """异步发送验证码邮件（在子线程中执行，不阻塞请求）"""
    now = time.time()
    _rate_limit_store[to_email] = now
    t = threading.Thread(target=_send_email_sync, args=(to_email, code), daemon=True)
    t.start()
