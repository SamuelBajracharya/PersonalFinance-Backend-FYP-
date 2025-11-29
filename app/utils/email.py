import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings


def send_otp_email(to_email: str, otp: str, purpose: str):
    # Define content for each OTP type
    purposes = {
        "account_verification": {
            "subject": "Verify Your Email - SaveMarga",
            "title": "Email Verification",
            "intro": "Thank you for signing up with <b>SaveMarga</b>.",
            "instruction": "Please use the following OTP to verify your account:",
            "icon": """
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" fill="#2B74F5" viewBox="0 0 24 24">
                  <path d="M12 1a11 11 0 1 0 11 11A11.013 11.013 0 0 0 12 1Zm0 19.933A8.933 8.933 0 1 1 20.933 12 8.944 8.944 0 0 1 12 20.933ZM10.293 13.707l-2-2a1 1 0 0 1 1.414-1.414L11 11.586l3.293-3.293a1 1 0 1 1 1.414 1.414l-4 4a1 1 0 0 1-1.414 0Z"/>
                </svg>
            """,
        },
        "two_factor_auth": {
            "subject": "Login Verification - SaveMarga",
            "title": "Two-Factor Authentication",
            "intro": "We detected a login attempt to your <b>SaveMarga</b> account.",
            "instruction": "Use the OTP below to complete your login:",
            "icon": """
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" fill="#2B74F5" viewBox="0 0 24 24">
                  <path d="M12 2a5 5 0 0 1 5 5v3h1a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h1V7a5 5 0 0 1 5-5Zm0 2a3 3 0 0 0-3 3v3h6V7a3 3 0 0 0-3-3Z"/>
                </svg>
            """,
        },
        "password_reset": {
            "subject": "Reset Your Password - SaveMarga",
            "title": "Password Reset Request",
            "intro": "We received a request to reset your <b>SaveMarga</b> account password.",
            "instruction": "Use the OTP below to reset your password:",
            "icon": """
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" fill="#2B74F5" viewBox="0 0 24 24">
                  <path d="M13 3a9 9 0 1 0 9 9h-2a7 7 0 1 1-7-7V3Zm0 4v5l4.28 2.54 1-1.74L14 11V7h-1Z"/>
                </svg>
            """,
        },
    }

    # Default to registration if purpose not recognized
    content = purposes.get(purpose, purposes["account_verification"])

    # HTML Email Template
    html_body = f"""
    <html>
      <body style="margin:0; padding:0; font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color:transparent; color:#FFFFFF;">
        <table align="center" width="100%" style="max-width:600px; background-color:#0C0C0C; border-radius:12px; overflow:hidden;">
          <tr>
            <td style="background-color:#FFAA2D; text-align:center; padding:25px 0;">
              <h1 style="margin:0; color:#0C0C0C; font-weight:800; font-size:26px;">SaveMarga</h1>
            </td>
          </tr>
          <tr>
            <td style="padding:35px;">
              <div style="text-align:center; margin-bottom:20px;">
                {content["icon"]}
              </div>
              <h2 style="text-align:center; color:#FFAA2D; margin-bottom:15px;">{content["title"]}</h2>
              <p style="text-align:center; color:#CCCCCC; font-size:15px;">
                {content["intro"]}<br><br>{content["instruction"]}
              </p>

              <div style="text-align:center; margin:30px 0;">
                <div style="display:inline-block; background-color:transparent; border:2px solid #2B74F5; border-radius:10px; padding:20px 50px; font-size:28px; font-weight:bold; color:#FFAA2D; letter-spacing:4px;">
                  {otp}
                </div>
              </div>

              <p style="color:#9CA3AF; font-size:13px; text-align:center; margin-top:10px;">
                This OTP will expire in <b>10 minutes</b>. Do not share it with anyone.
              </p>
            </td>
          </tr>
          <tr>
            <td style="background-color:transparent; text-align:center; padding:15px;">
              <p style="color:#6B7280; font-size:12px;">&copy; 2025 SaveMarga. All rights reserved.</p>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    # Plaintext Fallback
    text_body = f"""
{content['title']}
-----------------------
{content['intro']}
{content['instruction']}

Your OTP is: {otp}

This OTP will expire in 10 minutes. Do not share it with anyone.
"""

    # Build Email
    message = MIMEMultipart("alternative")
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to_email
    message["Subject"] = content["subject"]

    message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    # Send Email
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)
        print(f"✅ [{purpose}] OTP email sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send OTP email to {to_email}: {e}")
