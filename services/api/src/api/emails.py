"""Bilingual (EN/BN) transactional email content, wrapped in the branded shell."""

from __future__ import annotations

from api.mailer import render_email


def verify_welcome(name: str, link: str, lang: str) -> tuple[str, str, str]:
    """Welcome + email-confirmation, sent on signup. Returns (subject, html, text)."""
    bn = lang == "bn"
    if bn:
        subject = "ইমেইল নিশ্চিত করুন — Bulls of Dhaka"
        heading = f"স্বাগতম, {name}! 🐂"
        paras = [
            "Bulls of Dhaka-তে যোগ দেওয়ার জন্য ধন্যবাদ — DSE নিয়ে তথ্য, গুজব নয়।",
            "পাসওয়ার্ড রিসেট ও অ্যাকাউন্ট বার্তা পেতে আপনার ইমেইল নিশ্চিত করুন।",
        ]
        cta = "ইমেইল নিশ্চিত করুন"
        footer = "আপনি এই অ্যাকাউন্ট তৈরি না করে থাকলে এই ইমেইল উপেক্ষা করুন।"
    else:
        subject = "Confirm your email — Bulls of Dhaka"
        heading = f"Welcome, {name}! 🐂"
        paras = [
            "Thanks for joining Bulls of Dhaka — facts on the DSE, not rumours.",
            "Please confirm your email so you can reset your password and get account notices.",
        ]
        cta = "Confirm email"
        footer = "If you didn't create this account, you can safely ignore this email."
    html, text = render_email(
        heading=heading, paragraphs=paras, cta_label=cta, cta_url=link, footer=footer
    )
    return subject, html, text


def password_reset(name: str, link: str, lang: str) -> tuple[str, str, str]:
    bn = lang == "bn"
    if bn:
        subject = "পাসওয়ার্ড রিসেট — Bulls of Dhaka"
        heading = "পাসওয়ার্ড রিসেট করুন"
        paras = [
            f"হাই {name}, আপনার পাসওয়ার্ড রিসেটের একটি অনুরোধ পেয়েছি।",
            "নতুন পাসওয়ার্ড সেট করতে নিচের বোতামে ট্যাপ করুন। লিংকটি ৩০ মিনিটে মেয়াদ শেষ হবে।",
        ]
        cta = "নতুন পাসওয়ার্ড সেট করুন"
        footer = "অনুরোধ করেননি? আপনার পাসওয়ার্ড অপরিবর্তিত আছে — এই ইমেইল উপেক্ষা করুন।"
    else:
        subject = "Reset your password — Bulls of Dhaka"
        heading = "Reset your password"
        paras = [
            f"Hi {name}, we received a request to reset your password.",
            "Tap the button below to set a new one. This link expires in 30 minutes.",
        ]
        cta = "Set new password"
        footer = "Didn't request this? Your password is unchanged — you can ignore this email."
    html, text = render_email(
        heading=heading, paragraphs=paras, cta_label=cta, cta_url=link, footer=footer
    )
    return subject, html, text
