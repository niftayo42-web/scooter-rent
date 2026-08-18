# Skuter Rent — Live Timer, GPS & QR Payment App

A Flask + MySQL rental app for two scooter types (Child and Adult), with a live
rental timer, automatic pricing, GPS distance tracking, a private dashboard per
renter, and a staff-only revenue dashboard.

## How it works

- **Customer** picks Child or Adult scooter on the homepage, enters name + phone,
  **adds a photo of their ID** — they can tap "Take Photo" to use the camera or
  "Choose from Gallery" to pick an existing photo — and gets a **private link**
  (`/r/<token>`) — this is their own dashboard. No other renter's info is
  visible there, ever.
- Their dashboard shows a **live timer, live price, and live distance** (using
  the phone's GPS while riding).
- When they tap **"End Ride & Pay"**, the ride locks in and they see the total
  due. They can pay the **full amount or a partial amount**, choosing
  **Telebirr, CBE Birr, or Cash**. Telebirr/CBE show your QR code to scan. If
  they pay partially, the remaining balance stays open for another payment.
- Every payment gets its **own receipt number** (e.g. `RCT-000123`). Staff
  confirms each payment individually — only confirmed payments count as
  revenue, and the scooter becomes available again once the full price is
  paid (or staff uses **Force Complete** to write off a small remainder).
- Staff can issue a **refund** on any rental with money already confirmed —
  refunds get their own receipt number (e.g. `REF-000045`) and are
  subtracted from revenue totals automatically.
- If the customer allows it, the browser can show a **notification** when
  their ride ends or their payment is confirmed. Staff get a notification
  when a new payment is awaiting confirmation.
- **Staff dashboard** (PIN-protected, not visible to customers) shows Today /
  This Week / This Month revenue, all active rentals with amount paid /
  balance due, full receipt history, and rental history.

## Pricing (edit in `app.py` → `calc_price()`)

- **Child**: the first minute is covered by a flat **20 ETB** start fee — no
  extra charge is added during that first minute. After the first minute,
  **13 ETB/min** is added continuously, calculated to the exact second (not
  rounded up), e.g. 1 min 30 sec = 20 + 13×0.5 = **26.5 ETB**.
- **Adult**: no start fee, **30 ETB/min** continuously by the second, e.g.
  30 sec = **15 ETB**.

## 1. Install requirements

Open the project folder in VS Code, then in the terminal:

```
pip install -r requirements.txt
```

## 2. Set up the database in MySQL Workbench

**If you already ran `schema.sql` before this update** (i.e. your app was
working already), don't re-run `schema.sql` — it would wipe your data. Instead
run **`add_payment_tracking.sql`** the same way (File → Open SQL Script →
Execute). It adds the new `payments` table and columns without touching your
existing scooters, rentals, or history.

**If this is a brand-new setup:**
1. Open MySQL Workbench, connect to your local MySQL server.
2. Open `schema.sql` (File → Open SQL Script).
3. Click the lightning bolt icon (Execute) to run the whole script.
   This creates the `skuter_rent` database, all tables (including
   `payments`), a default staff PIN (`1234`), and a starter fleet of 3 child
   + 4 adult scooters.

## 3. Connect the app to your database

Open `app.py`, find this block near the top, and fill in your real MySQL
password:

```python
DB_CONFIG = dict(
    host="localhost",
    user="root",
    password="",   # <-- put your MySQL root password here
    database="skuter_rent",
    ...
)
```

## 4. Run it

```
python app.py
```

Open **http://localhost:5000** in your browser. To test on your phone (same
WiFi), use your PC's local IP instead, e.g. `http://192.168.1.5:5000`.

> **GPS note:** phone browsers only allow GPS access over `https://` or on
> `localhost`. Testing on your PC works fine. To track distance on a real
> phone in the field, you'll need to publish the app on a domain with HTTPS
> (see below) — until then, distance will simply stay at 0 on other devices
> and everything else (timer, price, payment) still works normally.

## 5. Already ran schema.sql before? Add the ID photo column

If you set up your database *before* this update, just run one more script in
MySQL Workbench: open `add_id_photo_column.sql` (File → Open SQL Script) and
click the lightning bolt to run it. This adds the missing column without
losing any of your existing scooters or data. (If this is your first time
setting up the database, skip this — `schema.sql` already includes it.)

## 6. Change the staff PIN

The default PIN is `1234`. Change it any time in MySQL Workbench:

```sql
UPDATE skuter_rent.staff SET pin = '5678' WHERE name = 'Admin';
```

## 7. Editing the QR codes

Your Telebirr and CBE Birr QR codes are already cropped and placed at:

```
static/images/telebirr_qr.png
static/images/cbe_qr.png
```

To update them later, just replace those two files with new cropped images
(same filenames).

## 8. Publishing to a real domain (so GPS + phone access work everywhere)

Same pattern as your other Skuter Rent site:
1. Get a small VPS or hosting plan that supports Python/Flask (e.g. PythonAnywhere,
   Render, or a shared host with SSH).
2. Copy the whole project folder over.
3. Point your MySQL connection at the hosted database (update `DB_CONFIG`).
4. Run behind a real WSGI server (e.g. `gunicorn app:app`) instead of
   `python app.py`, and put it behind HTTPS (most hosts do this for you, or
   use Let's Encrypt).

## Project structure

```
skuter_app/
  app.py                  Flask app (all routes)
  schema.sql               MySQL schema + starter data
  add_id_photo_column.sql  Migration if you set up the DB before this update
  requirements.txt
  templates/
    landing.html            Homepage — pick scooter type (3D animated scooter)
    start_rent.html          Name + phone form
    customer_dashboard.html  Private live dashboard (timer, price, distance, pay)
    staff_login.html         PIN login
    staff_dashboard.html     Revenue + active rentals + history
  static/
    css/style.css
    images/
      telebirr_qr.png       Cropped Telebirr QR
      cbe_qr.png             Cropped CBE Birr QR
      hero_bg.jpg             Background art
```

## Notes on the design choices

- **Customer isolation** is done with a private, unguessable link per rental
  (`/r/<long-random-token>`) rather than a login — simplest for a walk-up
  rental customer, and each token only ever shows that one rental's data.
- **Payment confirmation always requires staff** — a customer marking
  "I chose Telebirr" only sets it to *pending confirmation*; it does not
  count as revenue or close the rental until staff taps **Confirm Paid**.
  This matches what you asked for: payment method is registered by staff.
- **Distance (km)** is calculated from GPS points sent every few seconds
  while the ride is active, summed using the haversine formula.
