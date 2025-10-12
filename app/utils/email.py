import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings


def send_otp_email(to_email: str, otp: str):
    subject = "🔐 Verify Your Email - FastAPI App"

    # HTML template for the email
    html_body = f"""
    <html>
      <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f6f8; padding: 40px;">
        <table align="center" width="100%" style="max-width: 600px; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
          <tr>
            <td style="background-color: #4f46e5; padding: 20px 0; text-align: center; color: white;">
              <h2 style="margin: 0;">SaveMarga</h2>
            </td>
          </tr>
          <tr>
            <td style="padding: 30px;">
              <h3 style="color: #111827;">Email Verification</h3>
              <p style="color: #374151; font-size: 15px;">
                Hello 👋,<br><br>
                Thank you for signing up with <b>SaveMarga</b>.<br>
                Please use the following OTP to verify your account:
              </p>
              <div style="text-align: center; margin: 30px 0;">
                <div style="display: inline-block; background-color: #f9fafb; border: 2px dashed #4f46e5; border-radius: 8px; padding: 20px 40px; font-size: 24px; font-weight: bold; color: #1f2937; letter-spacing: 4px;">
                  {otp}
                </div>
              </div>
              <p style="color: #6b7280; font-size: 14px;">
                ⚠️ This OTP will expire in 10 minutes. Do not share it with anyone.
              </p>
              <p style="margin-top: 30px; color: #9ca3af; font-size: 13px; text-align: center;">
                If you did not request this, please ignore this email.
              </p>
            </td>
          </tr>
          <tr>
            <td style="background-color: #f3f4f6; text-align: center; padding: 15px; color: #6b7280; font-size: 13px;">
              &copy; 2025 FastAPI App. All rights reserved.
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    # Plaintext fallback
    text_body = f"Your OTP is: {otp}\n\nIf you did not request this, please ignore this email."

    message = MIMEMultipart("alternative")
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to_email
    message["Subject"] = subject

    # Attach both plain and HTML versions
    message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)
        print(f"✅ OTP email sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send OTP email to {to_email}: {e}")
