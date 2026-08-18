-- Run this in MySQL Workbench if you already created the skuter_rent database
-- before this update. It adds partial-payment / receipt / refund tracking
-- without losing any existing scooters, rentals, or history.
USE skuter_rent;

ALTER TABLE rentals
  ADD COLUMN amount_paid DECIMAL(10,2) NOT NULL DEFAULT 0 AFTER price;

-- Widen payment_status to allow 'partially_paid'
ALTER TABLE rentals
  MODIFY payment_status ENUM('unpaid','pending_confirmation','partially_paid','confirmed')
  NOT NULL DEFAULT 'unpaid';

-- Any rental that was already fully confirmed gets amount_paid backfilled
-- from its price, so past history stays consistent with the new columns.
UPDATE rentals SET amount_paid = price WHERE payment_status = 'confirmed';

CREATE TABLE IF NOT EXISTS payments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  rental_id INT NOT NULL,
  receipt_number VARCHAR(20) UNIQUE NULL,
  kind ENUM('payment','refund') NOT NULL DEFAULT 'payment',
  amount DECIMAL(10,2) NOT NULL,
  method ENUM('telebirr','cbe','cash') NOT NULL,
  status ENUM('pending_confirmation','confirmed') NOT NULL DEFAULT 'pending_confirmation',
  note VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  confirmed_by VARCHAR(50) NULL,
  confirmed_at DATETIME NULL,
  FOREIGN KEY (rental_id) REFERENCES rentals(id)
);

-- Backfill one payment record per already-confirmed rental, so old rentals
-- show up correctly in the new receipt history.
INSERT INTO payments (rental_id, receipt_number, kind, amount, method, status, confirmed_by, confirmed_at, created_at)
SELECT id, CONCAT('RCT-', LPAD(id, 6, '0')), 'payment', price, COALESCE(payment_method, 'cash'),
       'confirmed', confirmed_by, confirmed_at, COALESCE(end_time, created_at)
FROM rentals
WHERE payment_status = 'confirmed';
