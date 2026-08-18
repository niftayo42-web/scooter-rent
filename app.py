"""
Skuter Rent - Flask + MySQL rental app
Two scooter types (child / adult), live timer + price, GPS distance,
private per-renter dashboard (token-based, no login needed for customers),
staff-only PIN-protected revenue dashboard, Telebirr/CBE/Cash payment flow.
"""
import math
import os
import secrets
from datetime import datetime, date, timedelta
from functools import wraps

import pymysql
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort

app = Flask(__name__)
app.secret_key = "change-this-secret-key-before-deploying"

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "heic"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

# ---------------- Database config ----------------
DB_CONFIG = dict(
    host="127.0.0.1",
    user="root",
    password="corridor123",          # <-- put your MySQL root password here
    database="skuter_rent",
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=True,
)


def get_db():
    return pymysql.connect(**DB_CONFIG)


# ---------------- Payment account details ----------------
# Shown to customers on the payment screen (with a Copy button) so they can
# send money from their own Telebirr/CBE app even when they're viewing this
# page on that same phone (a QR code on-screen can't be scanned by the same
# device's camera).
PAYMENT_INFO = {
    "telebirr": {"number": "0906148655", "name": "Mebriet Mehari"},
    "cbe": {"number": "1000086565165", "name": "Mebriet Mehari"},
}


# ---------------- Pricing rules ----------------
# Child scooter: the first minute (0:00-1:00) is covered by the 20 birr start
# fee -- no per-minute charge is added during that first minute. After the
# first minute, 13 birr is added for every additional minute or part of a
# minute (billed in whole-minute steps, not by the second).
# Adult scooter: no start fee, 30 birr for every minute or part of a minute.
# Child Car (kids' ride-on car): no start fee, 30 birr for every minute or
# part of a minute -- same rate as Adult, just a different vehicle type.
def calc_price(scooter_type: str, seconds_elapsed: float) -> float:
    seconds_elapsed = max(0.0, seconds_elapsed)
    if scooter_type == "child":
        start_fee = 20
        if seconds_elapsed <= 60:
            return float(start_fee)
        extra_minutes = math.ceil((seconds_elapsed - 60) / 60)
        return float(start_fee + 13 * extra_minutes)
    minutes = max(1, math.ceil(seconds_elapsed / 60))
    return float(30 * minutes)


def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ================= Public / Customer routes =================

@app.route("/")
def landing():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT type, COUNT(*) AS available FROM scooters WHERE status='available' GROUP BY type")
        rows = cur.fetchall()
    db.close()
    avail = {"child": 0, "adult": 0, "child_car": 0}
    for r in rows:
        avail[r["type"]] = r["available"]
    return render_template("landing.html", avail=avail)


@app.route("/start/<scooter_type>", methods=["GET", "POST"])
def start_rent(scooter_type):
    if scooter_type not in ("child", "adult", "child_car"):
        abort(404)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        photo = request.files.get("id_photo")
        agreed = request.form.get("agree_waiver")

        if not name or not phone:
            return render_template("start_rent.html", scooter_type=scooter_type, error="Please fill in your name and phone number.")
        if not photo or photo.filename == "":
            return render_template("start_rent.html", scooter_type=scooter_type, error="Please take a photo of your ID before starting your ride.")
        if not allowed_file(photo.filename):
            return render_template("start_rent.html", scooter_type=scooter_type, error="That photo format isn't supported. Please use JPG or PNG.")
        if not agreed:
            return render_template("start_rent.html", scooter_type=scooter_type, error="Please agree to the safety & damage terms before starting your ride.")

        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT id FROM scooters WHERE type=%s AND status='available' LIMIT 1", (scooter_type,))
            scooter = cur.fetchone()
            if not scooter:
                db.close()
                return render_template("start_rent.html", scooter_type=scooter_type, error="No scooters of this type are available right now.")

            token = secrets.token_urlsafe(20)

            ext = secure_filename(photo.filename).rsplit(".", 1)[1].lower()
            photo_filename = f"{token}.{ext}"
            photo.save(os.path.join(UPLOAD_FOLDER, photo_filename))

            cur.execute(
                """INSERT INTO rentals (token, scooter_id, renter_name, renter_phone, renter_id_photo, scooter_type, start_time, status, waiver_agreed)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,'active',1)""",
                (token, scooter["id"], name, phone, photo_filename, scooter_type, datetime.now()),
            )
            cur.execute("UPDATE scooters SET status='rented' WHERE id=%s", (scooter["id"],))
        db.close()
        return redirect(url_for("customer_dashboard", token=token))

    return render_template("start_rent.html", scooter_type=scooter_type, error=None)


@app.route("/r/<token>")
def customer_dashboard(token):
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            """SELECT r.*, s.label AS scooter_label FROM rentals r
               JOIN scooters s ON s.id = r.scooter_id WHERE r.token=%s""",
            (token,),
        )
        rental = cur.fetchone()
    db.close()
    if not rental:
        abort(404)
    return render_template("customer_dashboard.html", rental=rental, token=token, payment_info=PAYMENT_INFO)


@app.route("/api/rental/<token>/status")
def api_rental_status(token):
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM rentals WHERE token=%s", (token,))
        rental = cur.fetchone()
    db.close()
    if not rental:
        return jsonify({"error": "not found"}), 404

    if rental["status"] == "active":
        elapsed = (datetime.now() - rental["start_time"]).total_seconds()
        price = calc_price(rental["scooter_type"], elapsed)
    else:
        elapsed = (rental["end_time"] - rental["start_time"]).total_seconds()
        price = float(rental["price"])

    amount_paid = float(rental["amount_paid"])
    balance_due = round(price - amount_paid, 2) if rental["status"] != "active" else None

    db2 = get_db()
    with db2.cursor() as cur:
        cur.execute("SELECT * FROM payments WHERE rental_id=%s ORDER BY id", (rental["id"],))
        payments = cur.fetchall()
    db2.close()

    return jsonify({
        "status": rental["status"],
        "elapsed_seconds": int(elapsed),
        "price": price,
        "distance_km": float(rental["distance_km"]),
        "payment_status": rental["payment_status"],
        "payment_method": rental["payment_method"],
        "amount_paid": amount_paid,
        "balance_due": balance_due,
        "payments": [
            {
                "id": p["id"],
                "receipt_number": p["receipt_number"],
                "kind": p["kind"],
                "amount": float(p["amount"]),
                "method": p["method"],
                "status": p["status"],
            }
            for p in payments
        ],
    })


@app.route("/api/rental/<token>/gps", methods=["POST"])
def api_rental_gps(token):
    data = request.get_json(force=True, silent=True) or {}
    lat, lng = data.get("lat"), data.get("lng")
    if lat is None or lng is None:
        return jsonify({"error": "missing coordinates"}), 400

    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT id, scooter_type, distance_km, status FROM rentals WHERE token=%s", (token,))
        rental = cur.fetchone()
        if not rental or rental["status"] != "active":
            db.close()
            return jsonify({"error": "not active"}), 400

        cur.execute("SELECT lat, lng FROM gps_points WHERE rental_id=%s ORDER BY id DESC LIMIT 1", (rental["id"],))
        last = cur.fetchone()

        new_distance = float(rental["distance_km"])
        if last:
            new_distance += haversine_km(float(last["lat"]), float(last["lng"]), lat, lng)

        cur.execute("INSERT INTO gps_points (rental_id, lat, lng) VALUES (%s,%s,%s)", (rental["id"], lat, lng))
        cur.execute("UPDATE rentals SET distance_km=%s WHERE id=%s", (round(new_distance, 3), rental["id"]))
    db.close()
    return jsonify({"distance_km": round(new_distance, 3)})


@app.route("/api/rental/<token>/end", methods=["POST"])
def api_rental_end(token):
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM rentals WHERE token=%s", (token,))
        rental = cur.fetchone()
        if not rental or rental["status"] != "active":
            db.close()
            return jsonify({"error": "not active"}), 400

        end_time = datetime.now()
        elapsed = (end_time - rental["start_time"]).total_seconds()
        price = calc_price(rental["scooter_type"], elapsed)

        cur.execute(
            "UPDATE rentals SET end_time=%s, price=%s, status='awaiting_payment' WHERE id=%s",
            (end_time, price, rental["id"]),
        )
    db.close()
    return jsonify({"price": price, "distance_km": float(rental["distance_km"]), "elapsed_seconds": int(elapsed)})


@app.route("/api/rental/<token>/pay", methods=["POST"])
def api_rental_pay(token):
    """Customer submits a payment (full or partial). Creates a payment row
    with its own receipt number; staff still has to confirm it before it
    counts as revenue or closes the rental."""
    data = request.get_json(force=True, silent=True) or {}
    method = data.get("method")
    if method not in ("telebirr", "cbe"):
        return jsonify({"error": "invalid method"}), 400

    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM rentals WHERE token=%s", (token,))
        rental = cur.fetchone()
        if not rental or rental["status"] != "awaiting_payment":
            db.close()
            return jsonify({"error": "not awaiting payment"}), 400

        balance_due = round(float(rental["price"]) - float(rental["amount_paid"]), 2)
        if balance_due <= 0:
            db.close()
            return jsonify({"error": "already paid in full"}), 400

        raw_amount = data.get("amount")
        try:
            amount = round(float(raw_amount), 2) if raw_amount is not None else balance_due
        except (TypeError, ValueError):
            db.close()
            return jsonify({"error": "invalid amount"}), 400

        if amount <= 0 or amount > balance_due + 0.01:
            db.close()
            return jsonify({"error": f"amount must be between 0 and {balance_due}"}), 400

        cur.execute(
            "SELECT id FROM payments WHERE rental_id=%s AND status='pending_confirmation'",
            (rental["id"],),
        )
        if cur.fetchone():
            db.close()
            return jsonify({"error": "a payment is already waiting for staff confirmation"}), 400

        cur.execute(
            """INSERT INTO payments (rental_id, kind, amount, method, status)
               VALUES (%s,'payment',%s,%s,'pending_confirmation')""",
            (rental["id"], amount, method),
        )
        payment_id = cur.lastrowid
        receipt_number = f"RCT-{payment_id:06d}"
        cur.execute("UPDATE payments SET receipt_number=%s WHERE id=%s", (receipt_number, payment_id))

        cur.execute(
            "UPDATE rentals SET payment_method=%s, payment_status='pending_confirmation' WHERE id=%s",
            (method, rental["id"]),
        )
    db.close()
    return jsonify({
        "ok": True, "method": method, "amount": amount,
        "receipt_number": receipt_number,
        "balance_due": round(balance_due - amount, 2),
    })


@app.route("/api/rental/<token>/cancel_payment", methods=["POST"])
def api_rental_cancel_payment(token):
    """Customer changed their mind about the payment method before staff
    confirmed it. Removes the still-pending payment row so they can submit
    a fresh one with a different method. Does nothing to already-confirmed
    payments -- those are locked in."""
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM rentals WHERE token=%s", (token,))
        rental = cur.fetchone()
        if not rental:
            db.close()
            return jsonify({"error": "not found"}), 404

        cur.execute(
            "SELECT * FROM payments WHERE rental_id=%s AND status='pending_confirmation' ORDER BY id DESC LIMIT 1",
            (rental["id"],),
        )
        pending = cur.fetchone()
        if not pending:
            db.close()
            return jsonify({"error": "no pending payment to cancel"}), 400

        cur.execute("DELETE FROM payments WHERE id=%s", (pending["id"],))

        new_status = "partially_paid" if float(rental["amount_paid"]) > 0 else "unpaid"
        cur.execute(
            "UPDATE rentals SET payment_status=%s, payment_method=NULL WHERE id=%s",
            (new_status, rental["id"]),
        )
    db.close()
    return jsonify({"ok": True})


# ================= Staff routes =================

def staff_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("staff_id"):
            return redirect(url_for("staff_login"))
        return f(*args, **kwargs)
    return wrapper


@app.route("/staff", methods=["GET", "POST"])
def staff_login():
    error = None
    if request.method == "POST":
        pin = request.form.get("pin", "").strip()
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT * FROM staff WHERE pin=%s", (pin,))
            staff = cur.fetchone()
        db.close()
        if staff:
            session["staff_id"] = staff["id"]
            session["staff_name"] = staff["name"]
            return redirect(url_for("staff_dashboard"))
        error = "Incorrect PIN."
    return render_template("staff_login.html", error=error)


@app.route("/staff/logout")
def staff_logout():
    session.clear()
    return redirect(url_for("staff_login"))


@app.route("/staff/api/change_pin", methods=["POST"])
@staff_required
def staff_api_change_pin():
    """Staff changes their own PIN from the dashboard. Requires the current
    PIN as confirmation, and the new PIN must be at least 4 digits and not
    already in use by another staff member."""
    data = request.get_json(force=True, silent=True) or {}
    current_pin = (data.get("current_pin") or "").strip()
    new_pin = (data.get("new_pin") or "").strip()

    if not new_pin or len(new_pin) < 4 or not new_pin.isdigit():
        return jsonify({"error": "New PIN must be at least 4 digits."}), 400

    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM staff WHERE id=%s", (session["staff_id"],))
        staff = cur.fetchone()
        if not staff or staff["pin"] != current_pin:
            db.close()
            return jsonify({"error": "Current PIN is incorrect."}), 400

        cur.execute("SELECT id FROM staff WHERE pin=%s AND id!=%s", (new_pin, staff["id"]))
        if cur.fetchone():
            db.close()
            return jsonify({"error": "That PIN is already in use by another staff account."}), 400

        cur.execute("UPDATE staff SET pin=%s WHERE id=%s", (new_pin, staff["id"]))
    db.close()
    return jsonify({"ok": True})


@app.route("/staff/dashboard")
@staff_required
def staff_dashboard():
    return render_template("staff_dashboard.html", staff_name=session.get("staff_name"))


@app.route("/staff/api/summary")
@staff_required
def staff_api_summary():
    db = get_db()
    with db.cursor() as cur:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        def revenue_since(since_date):
            # Net revenue = confirmed payments minus confirmed refunds, so
            # partial payments count once confirmed and refunds pull back out.
            cur.execute(
                """SELECT
                     COALESCE(SUM(CASE WHEN kind='payment' THEN amount ELSE 0 END),0) -
                     COALESCE(SUM(CASE WHEN kind='refund' THEN amount ELSE 0 END),0) AS total
                   FROM payments
                   WHERE status='confirmed' AND DATE(confirmed_at) >= %s""",
                (since_date,),
            )
            return float(cur.fetchone()["total"])

        today_total = revenue_since(today)
        week_total = revenue_since(week_start)
        month_total = revenue_since(month_start)

        cur.execute(
            """SELECT r.*, s.label AS scooter_label FROM rentals r
               JOIN scooters s ON s.id=r.scooter_id
               WHERE r.status IN ('active','awaiting_payment')
               ORDER BY r.start_time DESC"""
        )
        active = cur.fetchall()

        cur.execute(
            """SELECT r.*, s.label AS scooter_label FROM rentals r
               JOIN scooters s ON s.id=r.scooter_id
               WHERE r.status='completed'
               ORDER BY r.end_time DESC LIMIT 50"""
        )
        history = cur.fetchall()

        def payments_for(rental_id):
            cur.execute("SELECT * FROM payments WHERE rental_id=%s ORDER BY id", (rental_id,))
            return cur.fetchall()

        def ser_payment(p):
            return {
                "id": p["id"], "receipt_number": p["receipt_number"], "kind": p["kind"],
                "amount": float(p["amount"]), "method": p["method"], "status": p["status"],
                "note": p["note"],
                "created_at": p["created_at"].strftime("%Y-%m-%d %H:%M") if p["created_at"] else None,
                "confirmed_by": p["confirmed_by"],
            }

        def ser(r):
            amount_paid = float(r["amount_paid"])
            price = float(r["price"])
            return {
                "id": r["id"], "scooter_label": r["scooter_label"], "scooter_type": r["scooter_type"],
                "renter_name": r["renter_name"], "renter_phone": r["renter_phone"],
                "renter_id_photo": f"/static/uploads/{r['renter_id_photo']}" if r.get("renter_id_photo") else None,
                "start_time": r["start_time"].strftime("%Y-%m-%d %H:%M"),
                "end_time": r["end_time"].strftime("%Y-%m-%d %H:%M") if r["end_time"] else None,
                "distance_km": float(r["distance_km"]), "price": price,
                "amount_paid": amount_paid, "balance_due": round(price - amount_paid, 2),
                "status": r["status"], "payment_method": r["payment_method"],
                "payment_status": r["payment_status"],
                "payments": [ser_payment(p) for p in payments_for(r["id"])],
            }

        active_ser = [ser(r) for r in active]
        history_ser = [ser(r) for r in history]
    db.close()

    return jsonify({
        "today": today_total, "week": week_total, "month": month_total,
        "active": active_ser, "history": history_ser,
    })


@app.route("/staff/api/confirm_payment/<int:payment_id>", methods=["POST"])
@staff_required
def staff_api_confirm_payment(payment_id):
    """Staff confirms one payment row (full or partial). Rental only closes
    out (and the scooter becomes available again) once amount_paid reaches
    the full price."""
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM payments WHERE id=%s", (payment_id,))
        payment = cur.fetchone()
        if not payment or payment["status"] != "pending_confirmation":
            db.close()
            return jsonify({"error": "not found or already confirmed"}), 404

        cur.execute(
            "UPDATE payments SET status='confirmed', confirmed_by=%s, confirmed_at=%s WHERE id=%s",
            (session.get("staff_name"), datetime.now(), payment_id),
        )

        cur.execute("SELECT * FROM rentals WHERE id=%s", (payment["rental_id"],))
        rental = cur.fetchone()
        new_paid = round(float(rental["amount_paid"]) + float(payment["amount"]), 2)
        balance = round(float(rental["price"]) - new_paid, 2)

        if balance <= 0.01:
            cur.execute(
                """UPDATE rentals SET amount_paid=%s, payment_status='confirmed', status='completed',
                   confirmed_by=%s, confirmed_at=%s WHERE id=%s""",
                (new_paid, session.get("staff_name"), datetime.now(), rental["id"]),
            )
            cur.execute("UPDATE scooters SET status='available' WHERE id=%s", (rental["scooter_id"],))
        else:
            cur.execute(
                "UPDATE rentals SET amount_paid=%s, payment_status='partially_paid' WHERE id=%s",
                (new_paid, rental["id"]),
            )
    db.close()
    return jsonify({"ok": True, "balance_due": max(balance, 0)})


@app.route("/staff/api/force_complete/<int:rental_id>", methods=["POST"])
@staff_required
def staff_api_force_complete(rental_id):
    """Close a rental out even if the balance isn't fully paid (e.g. writing
    off a small remainder). Use sparingly -- it does not add any revenue."""
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM rentals WHERE id=%s", (rental_id,))
        rental = cur.fetchone()
        if not rental:
            db.close()
            return jsonify({"error": "not found"}), 404

        cur.execute(
            """UPDATE rentals SET status='completed', payment_status='confirmed',
               confirmed_by=%s, confirmed_at=%s WHERE id=%s""",
            (session.get("staff_name"), datetime.now(), rental_id),
        )
        cur.execute("UPDATE scooters SET status='available' WHERE id=%s", (rental["scooter_id"],))
    db.close()
    return jsonify({"ok": True})


@app.route("/staff/api/refund/<int:rental_id>", methods=["POST"])
@staff_required
def staff_api_refund(rental_id):
    """Staff issues a refund. Refunds are recorded and confirmed immediately
    (staff physically hands the money back), get their own receipt number,
    and are subtracted from amount_paid and from revenue totals."""
    data = request.get_json(force=True, silent=True) or {}
    reason = (data.get("reason") or "").strip()

    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM rentals WHERE id=%s", (rental_id,))
        rental = cur.fetchone()
        if not rental:
            db.close()
            return jsonify({"error": "not found"}), 404

        try:
            amount = round(float(data.get("amount")), 2)
        except (TypeError, ValueError):
            db.close()
            return jsonify({"error": "invalid amount"}), 400

        amount_paid = float(rental["amount_paid"])
        if amount <= 0 or amount > amount_paid + 0.01:
            db.close()
            return jsonify({"error": f"amount must be between 0 and {amount_paid}"}), 400

        method = rental["payment_method"] or "telebirr"
        cur.execute(
            """INSERT INTO payments (rental_id, kind, amount, method, status, note, confirmed_by, confirmed_at)
               VALUES (%s,'refund',%s,%s,'confirmed',%s,%s,%s)""",
            (rental_id, amount, method, reason, session.get("staff_name"), datetime.now()),
        )
        payment_id = cur.lastrowid
        receipt_number = f"REF-{payment_id:06d}"
        cur.execute("UPDATE payments SET receipt_number=%s WHERE id=%s", (receipt_number, payment_id))

        new_paid = round(amount_paid - amount, 2)
        price = float(rental["price"])
        if new_paid >= price - 0.01:
            new_status = "confirmed"
        elif new_paid > 0:
            new_status = "partially_paid"
        else:
            new_status = "unpaid"
        cur.execute("UPDATE rentals SET amount_paid=%s, payment_status=%s WHERE id=%s",
                    (new_paid, new_status, rental_id))
    db.close()
    return jsonify({"ok": True, "receipt_number": receipt_number, "amount_paid": new_paid})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
