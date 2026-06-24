# 💳 Billing Service (Stripe Webhook Microservice)

This is a lightweight **FastAPI-based billing microservice** used to handle Stripe payments across multiple applications.

It processes Stripe webhook events and maps successful payments to user plans and credits.

---

## 🚀 Features

- Stripe Payment Link support
- Webhook processing (`checkout.session.completed`)
- Plan → credits mapping
- Multi-app SaaS ready
- Docker + Render deployable
- Stateless and scalable design

---

## 🧠 Architecture

Stripe → Billing Service (FastAPI) → Your Apps / Database

- Stripe handles payments
- This service verifies events
- Your apps read updated user state

---

## 📦 Tech Stack

- FastAPI
- Stripe API
- Python 3.11
- Docker (optional)
- Render deployment ready

---

## ⚙️ Environment Variables

Create these in Render or `.env`:
